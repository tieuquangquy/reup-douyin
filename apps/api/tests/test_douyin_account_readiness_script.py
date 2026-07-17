from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from scripts.douyin_account_readiness import main
from src.enums import DouyinAccountConnectionStatus, DouyinAccountHealthStatus
from src.services.douyin_account_service import DouyinAccountReadinessRow


class DouyinAccountReadinessScriptTests(unittest.TestCase):
    def _row(self, **overrides: object) -> DouyinAccountReadinessRow:
        return DouyinAccountReadinessRow(
            account_id=overrides.get("account_id", uuid4()),
            display_name=overrides.get("display_name", "Douyin Browser Account"),
            is_default=overrides.get("is_default", False),
            status=overrides.get("status", DouyinAccountConnectionStatus.INVALID),
            health_status=overrides.get("health_status", DouyinAccountHealthStatus.UNKNOWN),
            soft_deleted=overrides.get("soft_deleted", False),
            has_browser_profile=overrides.get("has_browser_profile", False),
            browser_profile_id=overrides.get("browser_profile_id", None),
            browser_profile_path=overrides.get("browser_profile_path", None),
            profile_path_exists=overrides.get("profile_path_exists", False),
            browser_context_status=overrides.get("browser_context_status", "missing"),
            readiness_status=overrides.get("readiness_status", "NOT_READY"),
            blocking_reason=overrides.get("blocking_reason", "browser_profile_missing"),
            preflight_ran=overrides.get("preflight_ran", False),
            preflight_result=overrides.get("preflight_result", None),
            preflight_failure_code=overrides.get("preflight_failure_code", None),
            selected_fetch_path=overrides.get("selected_fetch_path", None),
        )

    def test_readiness_command_reports_no_accounts_clearly(self) -> None:
        db = MagicMock()
        service = MagicMock()
        service.readiness_rows.return_value = []

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        service.readiness_rows.assert_called_once_with(include_deleted=False, run_preflight=True)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["checked_account_count"], 0)
        self.assertEqual(payload["accounts"], [])

    def test_readiness_command_reports_missing_profile_clearly(self) -> None:
        db = MagicMock()
        service = MagicMock()
        service.readiness_rows.return_value = [
            self._row(
                has_browser_profile=False,
                readiness_status="NOT_READY",
                blocking_reason="browser_profile_missing",
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["accounts"][0]["has_browser_profile"], False)
        self.assertEqual(payload["accounts"][0]["blocking_reason"], "browser_profile_missing")

    def test_account_with_existing_profile_path_is_reported_as_browser_profile_backed(self) -> None:
        db = MagicMock()
        service = MagicMock()
        service.readiness_rows.return_value = [
            self._row(
                has_browser_profile=True,
                browser_profile_id="profile-1",
                browser_profile_path="profiles/profile-1",
                profile_path_exists=True,
                readiness_status="PROFILE_ATTACHED",
                blocking_reason=None,
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--skip-preflight"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertTrue(payload["accounts"][0]["has_browser_profile"])
        self.assertTrue(payload["accounts"][0]["profile_path_exists"])
        self.assertEqual(payload["accounts"][0]["browser_profile_id"], "profile-1")

    def test_readiness_command_can_set_default_account(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        service.set_default_account.return_value = MagicMock(id=account_id)
        service.readiness_rows.return_value = [
            self._row(
                account_id=account_id,
                is_default=True,
                has_browser_profile=True,
                browser_profile_id="profile-1",
                browser_profile_path="profiles/profile-1",
                profile_path_exists=True,
                readiness_status="READY",
                blocking_reason=None,
                preflight_ran=True,
                preflight_result="passed",
                selected_fetch_path="browser_profile",
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--set-default", "--account-id", str(account_id)])

        self.assertEqual(exit_code, 0)
        service.set_default_account.assert_called_once_with(account_id)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["actions"][0]["action"], "set_default")
        self.assertEqual(payload["target_account_id"], str(account_id))

    def test_revalidate_success_updates_account_to_ready(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.ACTIVE
        account.health_status = DouyinAccountHealthStatus.HEALTHY
        service.validate_account.return_value = (account, True, "browser_validation_success")
        service.readiness_rows.return_value = [
            self._row(
                account_id=account_id,
                status=DouyinAccountConnectionStatus.ACTIVE,
                health_status=DouyinAccountHealthStatus.HEALTHY,
                has_browser_profile=True,
                profile_path_exists=True,
                readiness_status="READY",
                blocking_reason=None,
                preflight_ran=True,
                preflight_result="passed",
                selected_fetch_path="browser_profile",
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--revalidate", "--timeout-seconds", "120"])

        self.assertEqual(exit_code, 0)
        service.validate_account.assert_called_once_with(account_id, validation_source="readiness_revalidate")
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["action"], "revalidate")
        self.assertEqual(payload["readiness_status"], "READY")
        self.assertEqual(payload["status"], "ACTIVE")
        self.assertEqual(payload["health_status"], "HEALTHY")

    def test_revalidate_failure_returns_manual_login_required(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.EXPIRED
        account.health_status = DouyinAccountHealthStatus.EXPIRED
        account.last_error_code = "expired_session"
        account.last_validation_status = "browser_validation_login_required"
        account.last_error_message = "login wall still shown"
        service.validate_account.return_value = (account, False, "browser_validation_login_required")
        service.readiness_rows.return_value = [
            self._row(
                account_id=account_id,
                status=DouyinAccountConnectionStatus.EXPIRED,
                health_status=DouyinAccountHealthStatus.EXPIRED,
                has_browser_profile=True,
                profile_path_exists=True,
                readiness_status="NOT_READY",
                blocking_reason="browser_validation_login_required",
                preflight_ran=True,
                preflight_result="failed",
                preflight_failure_code="account_not_fetch_ready",
                selected_fetch_path=None,
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--revalidate"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "manual_login_required")
        self.assertIn("--open-profile --timeout-seconds 300", payload["fallback_command"])

    def test_revalidate_failure_returns_captcha_required(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.BLOCKED
        account.last_error_code = "browser_validation_challenge_required"
        account.last_validation_status = "browser_validation_challenge_required"
        account.last_error_message = "browser_context_blocked_response"
        service.validate_account.return_value = (account, False, "browser_validation_challenge_required")
        service.readiness_rows.return_value = [
            self._row(
                account_id=account_id,
                status=DouyinAccountConnectionStatus.INVALID,
                health_status=DouyinAccountHealthStatus.BLOCKED,
                has_browser_profile=True,
                profile_path_exists=True,
                readiness_status="NOT_READY",
                blocking_reason="browser_validation_challenge_required",
                preflight_ran=True,
                preflight_result="failed",
                preflight_failure_code="account_not_fetch_ready",
                selected_fetch_path=None,
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--revalidate"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "captcha_required")

    def test_revalidate_failure_returns_browser_profile_locked(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.INVALID
        account.last_error_code = "browser_validation_runtime_unavailable"
        account.last_validation_status = "profile_reopen_failed"
        account.last_error_message = "profile_locked_by_existing_process:ProcessSingleton"
        service.validate_account.return_value = (account, False, "profile_reopen_failed")
        service.readiness_rows.return_value = [
            self._row(
                account_id=account_id,
                status=DouyinAccountConnectionStatus.INVALID,
                health_status=DouyinAccountHealthStatus.INVALID,
                has_browser_profile=True,
                profile_path_exists=True,
                readiness_status="NOT_READY",
                blocking_reason="profile_reopen_failed",
                preflight_ran=True,
                preflight_result="failed",
                preflight_failure_code="account_not_fetch_ready",
                selected_fetch_path=None,
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--revalidate"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "browser_profile_locked")
        self.assertIn("remove SingletonLock", payload["next_step"])

    def test_mark_challenge_solved_clears_stale_state_and_returns_revalidate_guidance(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.UNKNOWN
        service.clear_challenge_state_for_revalidation.return_value = account

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--mark-challenge-solved"])

        self.assertEqual(exit_code, 0)
        service.clear_challenge_state_for_revalidation.assert_called_once_with(account_id)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["action"], "mark_challenge_solved")
        self.assertEqual(payload["account_id"], str(account_id))
        self.assertEqual(payload["status"], "INVALID")
        self.assertEqual(payload["health_status"], "UNKNOWN")
        self.assertIn("--revalidate --timeout-seconds 120", payload["next_command"])

    def test_operator_confirm_ready_returns_operator_confirmed_guidance(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.UNKNOWN
        service.operator_confirm_ready.return_value = account

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--operator-confirm-ready"])

        self.assertEqual(exit_code, 0)
        service.operator_confirm_ready.assert_called_once_with(account_id)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["action"], "operator_confirm_ready")
        self.assertEqual(payload["readiness_status"], "OPERATOR_CONFIRMED")
        self.assertIn("Hydration may still hit captcha", payload["warning"])
        self.assertIn("hydrate_capture_session_metadata.py", payload["next_command"])

    def test_open_profile_reports_success_when_browser_context_opens(self) -> None:
        account_id = uuid4()
        workspace_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.workspace_id = workspace_id
        account.user_agent = "saved-agent"
        account.proxy_url = None
        account.metadata_json = {
            "browser_profile_id": "main",
            "browser_profile_path": "C:/profiles/main",
        }
        service.get_account.return_value = account
        registry = MagicMock()
        registry.open_profile_for_account.return_value = SimpleNamespace(
            status="active",
            browser_profile_id="main",
            browser_profile_path="C:/profiles/main",
        )
        registry.summary_for_account.side_effect = [
            SimpleNamespace(status="active"),
            SimpleNamespace(status="closed"),
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch(
            "src.services.douyin_browser_context_registry.douyin_browser_context_registry",
            registry,
        ), patch("scripts.douyin_account_readiness.time.monotonic", side_effect=[0, 0, 2]), patch(
            "scripts.douyin_account_readiness.time.sleep"
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--open-profile", "--timeout-seconds", "1"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["open_profile_status"], "opened")
        self.assertEqual(payload["account_id"], str(account_id))
        registry.close_for_account.assert_called_once()

    def test_open_profile_reports_browser_executable_missing_clearly(self) -> None:
        account_id = uuid4()
        workspace_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.workspace_id = workspace_id
        account.user_agent = "saved-agent"
        account.proxy_url = None
        account.metadata_json = {
            "browser_profile_id": "main",
            "browser_profile_path": "C:/profiles/main",
        }
        service.get_account.return_value = account
        registry = MagicMock()
        registry.open_profile_for_account.return_value = SimpleNamespace(
            status="invalid",
            reason="dependency_missing",
            browser_profile_path="C:/profiles/main",
        )

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch(
            "src.services.douyin_browser_context_registry.douyin_browser_context_registry",
            registry,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--open-profile", "--timeout-seconds", "1"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "browser_executable_missing")
        self.assertEqual(payload["recommended_command"], "python -m playwright install chromium")

    def test_open_profile_reports_profile_locked_clearly(self) -> None:
        account_id = uuid4()
        workspace_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.workspace_id = workspace_id
        account.user_agent = "saved-agent"
        account.proxy_url = None
        account.metadata_json = {
            "browser_profile_id": "main",
            "browser_profile_path": "C:/profiles/main",
        }
        service.get_account.return_value = account
        registry = MagicMock()
        registry.open_profile_for_account.return_value = SimpleNamespace(
            status="invalid",
            reason="profile_locked_by_existing_process:Error",
            browser_profile_path="C:/profiles/main",
        )

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch(
            "src.services.douyin_browser_context_registry.douyin_browser_context_registry",
            registry,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--open-profile", "--timeout-seconds", "1"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "profile_locked")
        self.assertIn("--open-profile --timeout-seconds 300", payload["recommended_command"])

    def test_revalidate_repeated_target_closed_error_returns_profile_open_failed(self) -> None:
        account_id = uuid4()
        db = MagicMock()
        service = MagicMock()
        account = MagicMock()
        account.id = account_id
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.INVALID
        account.last_error_code = "browser_validation_runtime_unavailable"
        account.last_validation_status = "profile_reopen_failed"
        account.last_error_message = "first_page_closed_early:TargetClosedError"
        service.validate_account.return_value = (account, False, "profile_reopen_failed")
        service.readiness_rows.return_value = [
            self._row(
                account_id=account_id,
                status=DouyinAccountConnectionStatus.INVALID,
                health_status=DouyinAccountHealthStatus.INVALID,
                has_browser_profile=True,
                profile_path_exists=True,
                readiness_status="NOT_READY",
                blocking_reason="profile_reopen_failed",
                preflight_ran=True,
                preflight_result="failed",
                preflight_failure_code="account_not_fetch_ready",
                selected_fetch_path=None,
            )
        ]

        with patch("src.db.session.get_session_factory", return_value=lambda: db), patch(
            "src.services.douyin_account_service.DouyinAccountService",
            return_value=service,
        ), patch("builtins.print") as print_mock:
            exit_code = main(["--account-id", str(account_id), "--revalidate"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(payload["code"], "profile_open_failed")
        self.assertEqual(payload["message"], "first_page_closed_early:TargetClosedError")
        self.assertIn("create a fresh browser profile", payload["next_step"])


if __name__ == "__main__":
    unittest.main()
