import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from src.enums import DouyinBrowserConnectSessionStatus
from src.models.source_accounts import DouyinBrowserConnectSession
from src.schemas.douyin_accounts import DouyinBrowserConnectStartRequest
from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry, _ContextRecord
from src.services.douyin_browser_connect_service import (
    DouyinBrowserConnectService,
    cookie_header_from_playwright_cookies,
    has_authenticated_douyin_cookies,
    playwright_runtime_error_parts,
)

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class DouyinBrowserConnectServiceTests(unittest.TestCase):
    def test_authenticated_cookie_detection_uses_session_cookie_names(self) -> None:
        cookies = [
            {"name": "passport_csrf_token", "value": "csrf", "domain": ".douyin.com"},
            {"name": "sessionid", "value": "secret-session", "domain": ".douyin.com"},
        ]

        self.assertTrue(has_authenticated_douyin_cookies(cookies))

    def test_cookie_header_filters_to_douyin_domains(self) -> None:
        cookies = [
            {"name": "sessionid", "value": "secret-session", "domain": ".douyin.com"},
            {"name": "sid_guard", "value": "secret-guard", "domain": ".douyin.com"},
            {"name": "unrelated", "value": "ignore", "domain": ".example.com"},
        ]

        header = cookie_header_from_playwright_cookies(cookies)

        self.assertIn("sessionid=secret-session", header)
        self.assertIn("sid_guard=secret-guard", header)
        self.assertNotIn("ignore", header)


    def test_parse_error_splits_code_and_message(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        code, message = service._parse_error("login_timed_out:Login did not complete in time")

        self.assertEqual(code, "login_timed_out")
        self.assertEqual(message, "Login did not complete in time")

    def test_failed_timeout_maps_to_timed_out_outcome(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        outcome = service._outcome_for(
            status=DouyinBrowserConnectSessionStatus.FAILED,
            error_code="login_timed_out",
        )

        self.assertEqual(outcome, "timed_out")

    def test_next_action_for_active_session_conflict(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        action = service._next_action(DouyinBrowserConnectSessionStatus.FAILED.value, "active_session_exists")

        self.assertEqual(action, "cancel_running_session_or_wait")

    def test_runtime_not_implemented_gets_actionable_code(self) -> None:
        code, message = playwright_runtime_error_parts("runtime_probe_failed", NotImplementedError())

        self.assertEqual(code, "runtime_not_supported")
        self.assertIn("event loop policy", message)

    def test_next_action_for_runtime_not_supported_uses_browser_setup_by_default(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        with patch("src.services.douyin_browser_connect_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_manual_import=False)):
            action = service._next_action(DouyinBrowserConnectSessionStatus.FAILED.value, "runtime_not_supported")

        self.assertEqual(action, "setup_browser_runtime")

    def test_next_action_for_runtime_not_supported_can_offer_legacy_manual_import(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        with patch("src.services.douyin_browser_connect_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_manual_import=True)):
            action = service._next_action(DouyinBrowserConnectSessionStatus.FAILED.value, "runtime_not_supported")

        self.assertEqual(action, "setup_runtime_or_manual_import")

    def test_waiting_login_session_becomes_stale_after_deadline(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)
        now = datetime.now(UTC)
        session = DouyinBrowserConnectSession(
            id=uuid4(),
            workspace_id=uuid4(),
            status=DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN,
            mode="browser_assisted",
            started_at=now - timedelta(minutes=10),
            updated_at=now - timedelta(minutes=10),
            metadata_json={"timeout_seconds": 180},
        )

        is_stale, reason = service._stale_state(session)

        self.assertTrue(is_stale)
        self.assertEqual(reason, "waiting_for_login_deadline_expired")

    def test_recent_waiting_login_session_can_resume(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)
        now = datetime.now(UTC)
        session = DouyinBrowserConnectSession(
            id=uuid4(),
            workspace_id=uuid4(),
            status=DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN,
            mode="browser_assisted",
            started_at=now - timedelta(seconds=10),
            updated_at=now - timedelta(seconds=10),
            metadata_json={"timeout_seconds": 180},
        )

        is_stale, reason = service._stale_state(session)

        self.assertFalse(is_stale)
        self.assertIsNone(reason)

    def test_session_capture_timeout_maps_to_timed_out_outcome(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        outcome = service._outcome_for(
            status=DouyinBrowserConnectSessionStatus.FAILED,
            error_code="session_capture_timed_out",
        )

        self.assertEqual(outcome, "timed_out")

    def test_reset_error_maps_to_cancelled_outcome(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        outcome = service._outcome_for(
            status=DouyinBrowserConnectSessionStatus.CANCELLED,
            error_code="reset_by_operator",
        )

        self.assertEqual(outcome, "cancelled")

    def test_validation_retry_ready_phase_uses_metadata(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)
        session = DouyinBrowserConnectSession(
            id=uuid4(),
            workspace_id=uuid4(),
            status=DouyinBrowserConnectSessionStatus.FAILED,
            mode="browser_assisted",
            last_error="validation_retry_ready:blocked_response_after_browser_prevalidation_passed",
            metadata_json={"browser_connect_phase": "validation_retry_ready"},
        )

        phase = service._phase_for_session(
            session=session,
            fallback_phase="failed",
            error_code="validation_retry_ready",
        )

        self.assertEqual(phase, "validation_retry_ready")

    def test_next_action_for_validation_retry_ready(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        action = service._next_action(DouyinBrowserConnectSessionStatus.FAILED.value, "validation_retry_ready")

        self.assertEqual(action, "retry_validation_or_reconnect")

    def test_blocked_post_login_prevalidation_offers_retry(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        retry = service._should_offer_validation_retry(
            reason="browser_context_blocked_retryable",
            capture_status="blocked",
        )

        self.assertTrue(retry)

    def test_login_required_post_login_prevalidation_does_not_offer_retry(self) -> None:
        service = object.__new__(DouyinBrowserConnectService)

        retry = service._should_offer_validation_retry(
            reason="expired_or_login_required",
            capture_status="blocked",
        )

        self.assertFalse(retry)

    def test_start_request_can_target_existing_account_profile(self) -> None:
        account_id = uuid4()

        request = DouyinBrowserConnectStartRequest(account_connection_id=account_id, timeout_seconds=180)

        self.assertEqual(request.account_connection_id, account_id)

    def test_account_profile_id_is_stable_across_reconnects(self) -> None:
        account_id = uuid4()
        registry = DouyinBrowserContextRegistry()

        profile_id = registry._profile_id_for_account(account_id)

        self.assertEqual(profile_id, f"account-{account_id}")

    def test_profile_identity_for_account_uses_existing_metadata_path(self) -> None:
        account_id = uuid4()
        registry = DouyinBrowserContextRegistry()

        profile_id, profile_path = registry.profile_identity_for_account(
            account_id,
            browser_profile_path="./data/browser-profiles/douyin/legacy-session-profile",
        )

        self.assertEqual(profile_id, "legacy-session-profile")
        self.assertTrue(profile_path.endswith("legacy-session-profile"))

    def test_profile_identity_match_rejects_different_profile(self) -> None:
        registry = DouyinBrowserContextRegistry()

        matches = registry.profile_identity_matches(
            expected_profile_id="account-a",
            expected_profile_path="./data/browser-profiles/douyin/account-a",
            actual_profile_id="session-b",
            actual_profile_path="./data/browser-profiles/douyin/session-b",
        )

        self.assertFalse(matches)

    def test_restart_preserves_derived_account_profile_target(self) -> None:
        account_id = uuid4()
        session = DouyinBrowserConnectSession(
            id=uuid4(),
            workspace_id=uuid4(),
            status=DouyinBrowserConnectSessionStatus.FAILED,
            mode="browser_assisted",
            derived_account_id=account_id,
        )
        service = object.__new__(DouyinBrowserConnectService)
        service.get_session = Mock(return_value=session)  # type: ignore[method-assign]
        service.start_connect = Mock(return_value=session)  # type: ignore[method-assign]

        request = DouyinBrowserConnectStartRequest(timeout_seconds=180)

        service.restart_session(session.id, request)

        sent_request = service.start_connect.call_args.args[0]
        self.assertEqual(sent_request.account_connection_id, account_id)

    def test_active_session_for_different_account_does_not_match_target(self) -> None:
        target_account_id = uuid4()
        other_account_id = uuid4()
        service = object.__new__(DouyinBrowserConnectService)
        session = DouyinBrowserConnectSession(
            id=uuid4(),
            workspace_id=uuid4(),
            status=DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN,
            mode="browser_assisted",
            derived_account_id=other_account_id,
        )

        self.assertFalse(service._active_session_matches_target(session, target_account_id))

    def test_persistent_profile_launch_retries_target_closed_with_bundled_chromium_first(self) -> None:
        registry = DouyinBrowserContextRegistry()
        profile_path = Mock()
        profile_path.__str__ = Mock(return_value="C:/profiles/profile-1")
        profile_path.mkdir = Mock()
        playwright = Mock()
        context = Mock()
        playwright.chromium.launch_persistent_context.side_effect = [Exception("TargetClosedError"), context]

        launched = registry._launch_persistent_context(
            playwright=playwright,
            profile_path=profile_path,
            user_agent="ua-1",
            launch_options={"headless": False},
        )

        self.assertIs(launched, context)
        self.assertEqual(playwright.chromium.launch_persistent_context.call_count, 2)
        first_call = playwright.chromium.launch_persistent_context.call_args_list[0]
        self.assertNotIn("channel", first_call.kwargs)
        self.assertEqual(first_call.args[0], "C:/profiles/profile-1")
        self.assertEqual(first_call.kwargs["user_agent"], "ua-1")

    def test_prevalidation_does_not_treat_generic_chinese_verify_word_as_blocked(self) -> None:
        registry = DouyinBrowserContextRegistry()
        context = Mock()
        page = Mock()
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        page.content.return_value = "抖音 登录验证 profile render_data"
        page.title.return_value = "抖音"
        page.url = "https://www.douyin.com/"

        status, reason = registry._prevalidate_record_context(context=context, page=page)

        self.assertEqual(status, "passed")
        self.assertEqual(reason, "authenticated_context_reachable")

    def test_validate_account_context_reacquires_open_page_when_remembered_page_closed(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        old_page = Mock()
        old_page.is_closed.return_value = True
        recovered_page = Mock()
        recovered_page.is_closed.return_value = False
        recovered_page.url = "https://www.douyin.com/user/profile"
        recovered_page.content.return_value = "douyin profile render_data"
        recovered_page.title.return_value = "Douyin"
        recovered_page.evaluate.return_value = "browser-agent"
        context = Mock()
        context.pages = [old_page, recovered_page]
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        record = _ContextRecord(
            runtime_context_id="runtime-1",
            browser_profile_id="profile-1",
            browser_profile_path="C:/profiles/profile-1",
            persistent_profile=True,
            workspace_id=uuid4(),
            connect_session_id=uuid4(),
            account_connection_id=account_id,
            playwright=Mock(),
            browser=None,
            context=context,
            page=old_page,
            user_agent="saved-agent",
            proxy_url=None,
            status="active",
            started_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC),
        )
        registry._records[record.runtime_context_id] = record

        with patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
            )

            result = registry.validate_account_context(account_id, validation_url="https://www.douyin.com/")

        self.assertTrue(result.available)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.runtime_attach_status, "managed_runtime_active")
        self.assertEqual(result.managed_runtime_status, "managed_runtime_active")
        self.assertEqual(result.page_recovery_status, "page_reacquired_same_context")
        self.assertIs(record.page, recovered_page)
        self.assertEqual(recovered_page.goto.call_count, 2)
        recovered_page.goto.assert_any_call("https://www.douyin.com/", wait_until="domcontentloaded", timeout=20_000)
        context.new_page.assert_not_called()

    def test_validate_account_context_creates_new_same_context_page_when_all_pages_closed(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        old_page = Mock()
        old_page.is_closed.return_value = True
        new_page = Mock()
        new_page.is_closed.return_value = False
        new_page.url = "https://www.douyin.com/"
        new_page.content.return_value = "douyin profile render_data"
        new_page.title.return_value = "Douyin"
        new_page.evaluate.return_value = "browser-agent"
        context = Mock()
        context.pages = [old_page]
        context.new_page.return_value = new_page
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        record = _ContextRecord(
            runtime_context_id="runtime-1",
            browser_profile_id="profile-1",
            browser_profile_path="C:/profiles/profile-1",
            persistent_profile=True,
            workspace_id=uuid4(),
            connect_session_id=uuid4(),
            account_connection_id=account_id,
            playwright=Mock(),
            browser=None,
            context=context,
            page=old_page,
            user_agent="saved-agent",
            proxy_url=None,
            status="active",
            started_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC),
        )
        registry._records[record.runtime_context_id] = record

        with patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
            )

            result = registry.validate_account_context(account_id, validation_url="https://www.douyin.com/")

        self.assertTrue(result.available)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.runtime_attach_status, "managed_runtime_active")
        self.assertEqual(result.managed_runtime_status, "managed_runtime_active")
        self.assertEqual(result.page_recovery_status, "page_created_same_context")
        self.assertIs(record.page, new_page)
        context.new_page.assert_called_once()
        self.assertEqual(new_page.goto.call_count, 2)
        new_page.goto.assert_any_call("https://www.douyin.com/", wait_until="domcontentloaded", timeout=20_000)

    def test_validate_account_context_retries_with_fresh_page_after_target_closed_during_navigation(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        old_page = Mock()
        old_page.is_closed.return_value = True
        first_new_page = Mock()
        first_new_page.is_closed.return_value = False
        first_new_page.goto.side_effect = Exception("TargetClosedError")
        second_new_page = Mock()
        second_new_page.is_closed.return_value = False
        second_new_page.url = "https://www.douyin.com/"
        second_new_page.content.return_value = "douyin profile render_data"
        second_new_page.title.return_value = "Douyin"
        second_new_page.evaluate.return_value = "browser-agent"
        context = Mock()
        context.pages = [old_page]
        context.new_page.side_effect = [first_new_page, second_new_page]
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        record = _ContextRecord(
            runtime_context_id="runtime-1",
            browser_profile_id="profile-1",
            browser_profile_path="C:/profiles/profile-1",
            persistent_profile=True,
            workspace_id=uuid4(),
            connect_session_id=uuid4(),
            account_connection_id=account_id,
            playwright=Mock(),
            browser=None,
            context=context,
            page=old_page,
            user_agent="saved-agent",
            proxy_url=None,
            status="active",
            started_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC),
        )
        registry._records[record.runtime_context_id] = record

        with patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
            )

            result = registry.validate_account_context(account_id, validation_url="https://www.douyin.com/")

        self.assertTrue(result.available)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.page_recovery_status, "page_created_same_context")
        self.assertIs(record.page, second_new_page)
        self.assertEqual(context.new_page.call_count, 2)

    def test_validate_account_context_returns_invalid_after_repeated_target_closed(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        old_page = Mock()
        old_page.is_closed.return_value = True
        first_new_page = Mock()
        first_new_page.is_closed.return_value = False
        first_new_page.goto.side_effect = Exception("TargetClosedError")
        second_new_page = Mock()
        second_new_page.is_closed.return_value = False
        second_new_page.goto.side_effect = Exception("TargetClosedError")
        context = Mock()
        context.pages = [old_page]
        context.new_page.side_effect = [first_new_page, second_new_page]
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        record = _ContextRecord(
            runtime_context_id="runtime-1",
            browser_profile_id="profile-1",
            browser_profile_path="C:/profiles/profile-1",
            persistent_profile=True,
            workspace_id=uuid4(),
            connect_session_id=uuid4(),
            account_connection_id=account_id,
            playwright=Mock(),
            browser=None,
            context=context,
            page=old_page,
            user_agent="saved-agent",
            proxy_url=None,
            status="active",
            started_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC),
        )
        registry._records[record.runtime_context_id] = record

        with patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
            )

            result = registry.validate_account_context(account_id, validation_url="https://www.douyin.com/")

        self.assertFalse(result.available)
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.runtime_attach_status, "runtime_attach_failed")
        self.assertEqual(result.page_recovery_status, "page_created_same_context")

    def test_reopen_profile_applies_windows_runtime_policy_and_attaches_same_profile(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        workspace_id = uuid4()
        page = Mock()
        context = Mock()
        context.pages = [page]
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        playwright = Mock()
        playwright.chromium.launch_persistent_context.return_value = context
        sync_manager = Mock()
        sync_manager.start.return_value = playwright
        sync_playwright = Mock(return_value=sync_manager)
        playwright_module = ModuleType("playwright")
        sync_api_module = ModuleType("playwright.sync_api")
        sync_api_module.sync_playwright = sync_playwright

        with patch.dict("sys.modules", {"playwright": playwright_module, "playwright.sync_api": sync_api_module}), patch(
            "src.services.douyin_browser_context_registry.ensure_windows_playwright_event_loop_policy"
        ) as policy, patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_persistent_browser_profile_enabled=True,
                douyin_user_agent="ua-1",
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
                douyin_persistent_browser_profiles_root_dir="./data/browser-profiles/douyin",
            )

            summary = registry.open_profile_for_account(
                workspace_id=workspace_id,
                account_connection_id=account_id,
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
                user_agent="saved-agent",
                proxy_url=None,
            )

        policy.assert_called_once()
        self.assertEqual(summary.status, "active")
        self.assertEqual(summary.reason, "reopen_success")
        self.assertEqual(summary.managed_runtime_status, "managed_runtime_active")
        self.assertIsNone(summary.profile_conflict_status)
        self.assertEqual(summary.account_connection_id, account_id)
        self.assertEqual(summary.browser_profile_id, "profile-1")
        self.assertEqual(Path(summary.browser_profile_path), Path("C:/profiles/profile-1"))
        self.assertIsNotNone(summary.runtime_context_id)
        playwright.chromium.launch_persistent_context.assert_called_once()
        first_call = playwright.chromium.launch_persistent_context.call_args
        self.assertEqual(Path(first_call.args[0]), Path("C:/profiles/profile-1"))
        self.assertEqual(first_call.kwargs["user_agent"], "saved-agent")
        self.assertEqual(registry.summary_for_account(account_id).runtime_context_id, summary.runtime_context_id)

    def test_reopen_profile_creates_new_page_when_first_page_is_closed_early(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        workspace_id = uuid4()
        closed_page = Mock()
        closed_page.is_closed.return_value = True
        new_page = Mock()
        new_page.is_closed.return_value = False
        new_page.url = "https://www.douyin.com/"
        context = Mock()
        context.pages = [closed_page]
        context.new_page.return_value = new_page
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        playwright = Mock()
        playwright.chromium.launch_persistent_context.return_value = context
        sync_manager = Mock()
        sync_manager.start.return_value = playwright
        sync_playwright = Mock(return_value=sync_manager)
        playwright_module = ModuleType("playwright")
        sync_api_module = ModuleType("playwright.sync_api")
        sync_api_module.sync_playwright = sync_playwright

        with patch.dict("sys.modules", {"playwright": playwright_module, "playwright.sync_api": sync_api_module}), patch(
            "src.services.douyin_browser_context_registry.ensure_windows_playwright_event_loop_policy"
        ), patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_persistent_browser_profile_enabled=True,
                douyin_user_agent="ua-1",
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
                douyin_persistent_browser_profiles_root_dir="./data/browser-profiles/douyin",
            )

            summary = registry.open_profile_for_account(
                workspace_id=workspace_id,
                account_connection_id=account_id,
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
                user_agent="saved-agent",
                proxy_url=None,
            )

        self.assertEqual(summary.status, "active")
        self.assertEqual(summary.managed_runtime_status, "managed_runtime_active")
        context.new_page.assert_called_once()

    def test_reopen_profile_classifies_page_recovery_failure_as_managed_runtime_reopen_failed(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        workspace_id = uuid4()
        context = Mock()
        context.pages = []
        context.cookies.return_value = [{"name": "sessionid", "value": "secret", "domain": ".douyin.com"}]
        context.new_page.side_effect = Exception("TargetClosedError")
        playwright = Mock()
        playwright.chromium.launch_persistent_context.return_value = context
        sync_manager = Mock()
        sync_manager.start.return_value = playwright
        sync_playwright = Mock(return_value=sync_manager)
        playwright_module = ModuleType("playwright")
        sync_api_module = ModuleType("playwright.sync_api")
        sync_api_module.sync_playwright = sync_playwright

        with patch.dict("sys.modules", {"playwright": playwright_module, "playwright.sync_api": sync_api_module}), patch(
            "src.services.douyin_browser_context_registry.ensure_windows_playwright_event_loop_policy"
        ), patch("src.services.douyin_browser_context_registry.get_settings") as get_settings, patch(
            "src.services.douyin_browser_context_registry.time.sleep"
        ):
            get_settings.return_value = SimpleNamespace(
                douyin_persistent_browser_profile_enabled=True,
                douyin_user_agent="ua-1",
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
                douyin_persistent_browser_profiles_root_dir="./data/browser-profiles/douyin",
            )

            summary = registry.open_profile_for_account(
                workspace_id=workspace_id,
                account_connection_id=account_id,
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
                user_agent="saved-agent",
                proxy_url=None,
            )

        self.assertEqual(summary.status, "invalid")
        self.assertEqual(summary.managed_runtime_status, "managed_runtime_reopen_failed")
        self.assertTrue(str(summary.reason).startswith("managed_runtime_reopen_failed"))
        self.assertEqual(context.new_page.call_count, 3)
        self.assertIsNone(registry.summary_for_account(account_id).runtime_context_id)

    def test_get_or_create_live_page_reacquires_page_after_target_closed_on_first_new_page_attempt(self) -> None:
        registry = DouyinBrowserContextRegistry()
        recovered_page = Mock()
        recovered_page.is_closed.return_value = False
        recovered_page.url = "https://www.douyin.com/"
        context = Mock()
        context.pages = []

        def new_page_side_effect():
            context.pages = [recovered_page]
            raise Exception("TargetClosedError")

        context.new_page.side_effect = new_page_side_effect

        page, status = registry.get_or_create_live_page(context=context, preferred_page=None)

        self.assertIs(page, recovered_page)
        self.assertEqual(status, "page_reacquired_same_context")

    def test_reopen_profile_classifies_not_implemented_as_runtime_not_supported(self) -> None:
        registry = DouyinBrowserContextRegistry()
        sync_manager = Mock()
        sync_manager.start.side_effect = NotImplementedError()
        sync_playwright = Mock(return_value=sync_manager)
        playwright_module = ModuleType("playwright")
        sync_api_module = ModuleType("playwright.sync_api")
        sync_api_module.sync_playwright = sync_playwright

        with patch.dict("sys.modules", {"playwright": playwright_module, "playwright.sync_api": sync_api_module}), patch(
            "src.services.douyin_browser_context_registry.ensure_windows_playwright_event_loop_policy"
        ) as policy, patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_persistent_browser_profile_enabled=True,
                douyin_user_agent="ua-1",
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
                douyin_persistent_browser_profiles_root_dir="./data/browser-profiles/douyin",
            )

            summary = registry.open_profile_for_account(
                workspace_id=uuid4(),
                account_connection_id=uuid4(),
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
                user_agent="saved-agent",
                proxy_url=None,
            )

        policy.assert_called_once()
        self.assertEqual(summary.status, "invalid")
        self.assertEqual(summary.reason, "reopen_not_supported_current_runtime:NotImplementedError")
        self.assertEqual(summary.managed_runtime_status, "managed_runtime_missing")
        self.assertIsNone(summary.profile_conflict_status)

    def test_reopen_profile_classifies_profile_lock_as_external_unmanaged_conflict(self) -> None:
        registry = DouyinBrowserContextRegistry()
        playwright = Mock()
        playwright.chromium.launch_persistent_context.side_effect = Exception(
            "ProcessSingleton: user data directory is already in use"
        )
        sync_manager = Mock()
        sync_manager.start.return_value = playwright
        sync_playwright = Mock(return_value=sync_manager)
        playwright_module = ModuleType("playwright")
        sync_api_module = ModuleType("playwright.sync_api")
        sync_api_module.sync_playwright = sync_playwright

        with patch.dict("sys.modules", {"playwright": playwright_module, "playwright.sync_api": sync_api_module}), patch(
            "src.services.douyin_browser_context_registry.ensure_windows_playwright_event_loop_policy"
        ) as policy, patch("src.services.douyin_browser_context_registry.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_persistent_browser_profile_enabled=True,
                douyin_user_agent="ua-1",
                douyin_browser_context_idle_timeout_seconds=3600,
                douyin_browser_context_max_lifetime_seconds=7200,
                douyin_persistent_browser_profiles_root_dir="./data/browser-profiles/douyin",
            )

            summary = registry.open_profile_for_account(
                workspace_id=uuid4(),
                account_connection_id=uuid4(),
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
                user_agent="saved-agent",
                proxy_url=None,
            )

        policy.assert_called_once()
        self.assertEqual(summary.status, "invalid")
        self.assertTrue(summary.reason.startswith("profile_locked_by_existing_process"))
        self.assertEqual(summary.managed_runtime_status, "profile_opened_outside_managed_runtime")
        self.assertEqual(summary.profile_conflict_status, "profile_opened_outside_managed_runtime")


if __name__ == "__main__":
    unittest.main()
