from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.enums import DouyinAccountConnectionStatus, DouyinAccountHealthStatus, DouyinAccountWarningLevel
from src.schemas.douyin_accounts import DouyinAccountCreateRequest
from src.services.douyin_account_service import DOUYIN_ACCOUNT_FRESH_WINDOW, DouyinAccountError, DouyinAccountService

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class DouyinAccountServiceTests(unittest.TestCase):
    def test_session_cookie_is_not_returned_in_response(self) -> None:
        service = DouyinAccountService(Mock())
        cookie = "sessionid=secret-cookie-value; sid_guard=another-secret"
        blob = service._encode_session_cookie(cookie)
        account = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            display_name="Creator account",
            douyin_user_id=None,
            status=DouyinAccountConnectionStatus.ACTIVE,
            is_default=True,
            session_secret_blob=blob,
            user_agent="agent",
            proxy_url=None,
            headers_json=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            last_validated_at=None,
            last_successful_validation_at=datetime(2026, 4, 22, tzinfo=UTC),
            last_validation_status="session_reachable",
            validation_source="manual_validate",
            next_validation_due_at=datetime(2026, 4, 22, tzinfo=UTC) + DOUYIN_ACCOUNT_FRESH_WINDOW,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            warning_summary_json=None,
            metadata_json=None,
            notes=None,
            created_at=datetime(2026, 4, 22, tzinfo=UTC),
            updated_at=datetime(2026, 4, 22, tzinfo=UTC),
        )

        response = service.to_response(account)

        self.assertTrue(response.session_cookie_present)
        self.assertNotEqual(response.session_cookie_preview, cookie)
        self.assertNotIn("secret-cookie-value", response.session_cookie_preview or "")

    def test_runtime_config_decodes_local_blob(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie("sessionid=abc"),
            user_agent="custom-agent",
            proxy_url="http://127.0.0.1:8080",
            last_successful_validation_at=datetime(2026, 4, 22, tzinfo=UTC),
            last_validated_at=datetime(2026, 4, 22, tzinfo=UTC),
            next_validation_due_at=datetime(2026, 4, 22, tzinfo=UTC) + DOUYIN_ACCOUNT_FRESH_WINDOW,
            expires_at=None,
            last_validation_status="session_reachable",
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        runtime = service.resolve_runtime_config(account_id)

        self.assertEqual(runtime.session_cookie, "sessionid=abc")
        self.assertEqual(runtime.user_agent, "custom-agent")
        self.assertEqual(runtime.proxy_url, "http://127.0.0.1:8080")

    def test_runtime_config_normalizes_manual_cookie_export_json(self) -> None:
        account_id = uuid4()
        cookie_export = '{"cookies":[{"name":"sessionid","value":"abc"},{"name":"sid_guard","value":"xyz"}]}'
        account = SimpleNamespace(
            id=account_id,
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie(cookie_export),
            user_agent=None,
            proxy_url=None,
            headers_json={"User-Agent": "header-agent"},
            last_successful_validation_at=datetime(2026, 4, 22, tzinfo=UTC),
            last_validated_at=datetime(2026, 4, 22, tzinfo=UTC),
            next_validation_due_at=datetime(2026, 4, 22, tzinfo=UTC) + DOUYIN_ACCOUNT_FRESH_WINDOW,
            expires_at=None,
            last_validation_status="session_reachable",
            metadata_json={"connection_source": "manual_import"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        runtime = service.resolve_runtime_config(account_id)

        self.assertEqual(runtime.session_cookie, "sessionid=abc; sid_guard=xyz")
        self.assertEqual(runtime.user_agent, "header-agent")
        db.commit.assert_called_once()

    def test_manual_import_missing_user_agent_is_rejected(self) -> None:
        service = DouyinAccountService(Mock())

        with self.assertRaises(DouyinAccountError) as ctx:
            service._normalize_imported_session(
                '{"cookies":[{"name":"sessionid","value":"abc"}]}',
                explicit_user_agent=None,
                headers_json=None,
                require_user_agent=True,
            )

        self.assertEqual(ctx.exception.code, "imported_session_missing_user_agent")

    def test_manual_import_json_parse_failure_is_classified(self) -> None:
        service = DouyinAccountService(Mock())

        with self.assertRaises(DouyinAccountError) as ctx:
            service._normalize_imported_session(
                '{"cookies":[{"name":"sessionid","value":"abc"}]',
                explicit_user_agent="ua-1",
                headers_json=None,
                require_user_agent=True,
                enforce_cookie_strength=True,
            )

        self.assertEqual(ctx.exception.code, "imported_session_cookie_parse_failed")

    def test_manual_import_cookie_too_thin_is_rejected(self) -> None:
        service = DouyinAccountService(Mock())

        with self.assertRaises(DouyinAccountError) as ctx:
            service._normalize_imported_session(
                "ttwid=abc; msToken=xyz",
                explicit_user_agent="ua-1",
                headers_json=None,
                require_user_agent=True,
                enforce_cookie_strength=True,
            )

        self.assertEqual(ctx.exception.code, "imported_session_cookie_too_thin")

    def test_create_account_skips_manual_import_smoke_validation_by_default(self) -> None:
        db = Mock()
        service = DouyinAccountService(db)
        request = DouyinAccountCreateRequest(
            workspace_id=uuid4(),
            display_name="Manual account",
            session_cookie='{"cookies":[{"name":"sessionid","value":"abc"}],"headers":{"User-Agent":"ua-1"}}',
            user_agent=None,
            is_default=False,
            metadata_json={"connection_source": "manual_import"},
        )
        service.validate_account = Mock()  # type: ignore[method-assign]

        created = service.create_account(request)

        self.assertEqual(created.user_agent, "ua-1")
        self.assertEqual(service._decode_session_cookie(created.session_secret_blob), "sessionid=abc")
        self.assertEqual(created.metadata_json["session_runtime_shape"], "cookie_header_v1")
        self.assertEqual(created.metadata_json["session_import_format"], "json_cookie_export")
        service.validate_account.assert_not_called()

    def test_create_account_runs_manual_import_smoke_validation_when_legacy_enabled(self) -> None:
        db = Mock()
        service = DouyinAccountService(db)
        request = DouyinAccountCreateRequest(
            workspace_id=uuid4(),
            display_name="Manual account",
            session_cookie='{"cookies":[{"name":"sessionid","value":"abc"}],"headers":{"User-Agent":"ua-1"}}',
            user_agent=None,
            is_default=False,
            metadata_json={"connection_source": "manual_import"},
        )

        validated_account = None

        def fake_validate(account_id, *, validation_url=None, validation_source="manual_validate"):
            nonlocal validated_account
            validated_account = db.add.call_args[0][0]
            return validated_account, True, "usable_for_fetch"

        service.validate_account = Mock(side_effect=fake_validate)  # type: ignore[method-assign]

        with patch("src.services.douyin_account_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_manual_import=True)):
            created = service.create_account(request)

        self.assertIs(created, validated_account)
        service.validate_account.assert_called_once()

    def test_to_response_hides_manual_import_preflight_summary_by_default(self) -> None:
        service = DouyinAccountService(Mock())
        account = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            display_name="Imported account",
            douyin_user_id=None,
            status=DouyinAccountConnectionStatus.BLOCKED,
            is_default=False,
            session_secret_blob=service._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="ua-1",
            proxy_url=None,
            headers_json={"User-Agent": "ua-1"},
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            last_validated_at=datetime(2026, 4, 23, tzinfo=UTC),
            last_successful_validation_at=None,
            last_validation_status="blocked_response",
            validation_source="manual_import_smoke",
            next_validation_due_at=datetime(2026, 4, 23, tzinfo=UTC),
            expires_at=None,
            last_error_code="blocked_response",
            last_error_message="blocked_response",
            warning_summary_json={"reason": "blocked_response"},
            metadata_json={"connection_source": "manual_import", "session_import_format": "json_cookie_export"},
            notes=None,
            created_at=datetime(2026, 4, 23, tzinfo=UTC),
            updated_at=datetime(2026, 4, 23, tzinfo=UTC),
        )

        response = service.to_response(account)

        self.assertIsNone(response.manual_import_preflight)
        self.assertEqual(response.browser_health_alignment.interactive_browser_state, "missing")
        self.assertEqual(response.browser_health_alignment.detached_http_state, "disabled")
        self.assertEqual(response.browser_health_alignment.effective_validation_path, "browser_profile")

    def test_to_response_exposes_browser_health_alignment_summary(self) -> None:
        service = DouyinAccountService(Mock())
        account = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            display_name="Browser account",
            douyin_user_id="user-1",
            status=DouyinAccountConnectionStatus.ACTIVE,
            is_default=True,
            session_secret_blob=service._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="ua-1",
            proxy_url=None,
            headers_json={"User-Agent": "ua-1"},
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_validation_status="browser_context_session_reachable",
            validation_source="browser_manual_validate",
            next_validation_due_at=datetime(2026, 4, 25, tzinfo=UTC),
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            warning_summary_json=None,
            metadata_json={
                "connection_source": "browser_assisted",
                "browser_profile_id": "profile-1",
                "last_browser_context_status": "passed",
                "last_browser_context_reason": "browser_context_session_reachable",
                "browser_context_checked_at": "2026-04-24T00:00:00+00:00",
            },
            notes=None,
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )

        response = service.to_response(account)

        self.assertEqual(response.browser_health_alignment.interactive_browser_state, "saved")
        self.assertEqual(response.browser_health_alignment.automated_browser_validation_state, "passed")
        self.assertEqual(response.browser_health_alignment.detached_http_state, "disabled")
        self.assertEqual(response.browser_health_alignment.effective_validation_path, "browser_profile")
        self.assertEqual(response.browser_health_alignment.expected_intake_path, "browser_profile")
        self.assertTrue(response.browser_health_alignment.validation_intake_aligned)
        self.assertTrue(response.browser_health_alignment.stale_blocked_state_cleared)
        self.assertEqual(response.browser_health_alignment.browser_evidence_strength, "strong")
        self.assertEqual(response.browser_health_alignment.last_browser_validation_status, "passed")
        self.assertEqual(response.browser_health_alignment.last_browser_validation_reason, "browser_context_session_reachable")
        self.assertEqual(
            response.browser_health_alignment.last_browser_validation_at,
            datetime(2026, 4, 24, 0, 0, tzinfo=UTC),
        )

    def test_browser_validation_success_clears_stale_blocked_state(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.BLOCKED,
            session_secret_blob=None,
            user_agent=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="blocked_response",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="blocked_response",
            last_error_message="old blocked state",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "blocked_response"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._ensure_persistent_profile_context = Mock()  # type: ignore[method-assign]
        browser_result = SimpleNamespace(
            status="passed",
            reason="authenticated_context_reachable",
            cookie_header="sessionid=abc; sid_guard=xyz",
            user_agent="browser-agent",
            runtime_context_id="runtime-1",
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(douyin_reuse_live_browser_for_validation=True)
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.validate_account_context.return_value = browser_result

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertTrue(valid)
        self.assertEqual(reason, "browser_validation_success")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.ACTIVE)
        self.assertEqual(account.last_validation_status, "browser_validation_success")
        self.assertIsNone(account.last_error_code)
        self.assertIsNone(account.last_error_message)
        self.assertIsNotNone(account.last_successful_validation_at)
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.HEALTHY)
        self.assertEqual(account.warning_level, DouyinAccountWarningLevel.NONE)
        self.assertEqual(account.metadata_json["last_browser_validation_category"], "browser_validation_success")
        self.assertEqual(account.metadata_json["browser_context_blocked_count"], 0)
        self.assertEqual(service._decode_session_cookie(account.session_secret_blob), "sessionid=abc; sid_guard=xyz")
        self.assertEqual(account.user_agent, "browser-agent")

    def test_browser_validation_inconclusive_does_not_fall_through_to_detached_http_or_hard_block(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.BLOCKED,
            session_secret_blob=None,
            user_agent=None,
            metadata_json={"browser_profile_id": "profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="blocked_response",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="blocked_response",
            last_error_message="old blocked state",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "blocked_response"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._ensure_persistent_profile_context = Mock()  # type: ignore[method-assign]
        service.build_fetch_client = Mock()  # type: ignore[method-assign]
        browser_result = SimpleNamespace(
            status="uncertain",
            reason="browser_prevalidation_no_positive_page_signal",
            cookie_header="sessionid=abc",
            user_agent="browser-agent",
            runtime_context_id="runtime-1",
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(douyin_reuse_live_browser_for_validation=True)
            registry.profile_identity_for_account.return_value = ("profile-1", None)
            registry.validate_account_context.return_value = browser_result

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "browser_validation_inconclusive")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.INVALID)
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.UNKNOWN)
        self.assertEqual(account.warning_level, DouyinAccountWarningLevel.WARN)
        self.assertEqual(account.last_validation_status, "browser_validation_inconclusive")
        self.assertEqual(account.last_error_code, "browser_validation_inconclusive")
        self.assertEqual(account.metadata_json["last_browser_validation_category"], "browser_validation_inconclusive")
        service.build_fetch_client.assert_not_called()

    def test_browser_validation_blocked_probe_requires_challenge_for_reusable_profile(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.BLOCKED,
            session_secret_blob=None,
            user_agent=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="blocked_response",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="blocked_response",
            last_error_message="old blocked state",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "blocked_response"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._ensure_persistent_profile_context = Mock()  # type: ignore[method-assign]
        service.build_fetch_client = Mock()  # type: ignore[method-assign]
        browser_result = SimpleNamespace(
            status="blocked",
            reason="browser_context_blocked_response",
            cookie_header="sessionid=abc; sid_guard=xyz",
            user_agent="browser-agent",
            runtime_context_id="runtime-1",
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(douyin_reuse_live_browser_for_validation=True)
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.validate_account_context.return_value = browser_result

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "browser_validation_challenge_required")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.INVALID)
        self.assertEqual(account.last_validation_status, "challenge_waiting_for_manual_verification")
        self.assertEqual(account.last_error_code, "browser_validation_challenge_required")
        self.assertEqual(account.last_error_message, "browser_context_blocked_response")
        self.assertEqual(account.metadata_json["last_browser_validation_category"], "browser_validation_challenge_required")
        self.assertEqual(account.metadata_json["last_browser_validation_final_category"], "browser_validation_challenge_required")
        self.assertEqual(account.metadata_json["last_browser_validation_blocked_probe_reason"], "browser_context_blocked_response")
        self.assertEqual(account.metadata_json["last_browser_validation_challenge_category"], "challenge_required")
        self.assertEqual(account.metadata_json["last_browser_validation_recommended_next_action"], "complete_challenge_in_browser_profile")
        self.assertTrue(account.metadata_json["douyin_challenge_detected"])
        self.assertEqual(account.metadata_json["douyin_challenge_state"], "challenge_waiting_for_manual_verification")
        self.assertEqual(account.metadata_json["douyin_challenge_category"], "challenge_required")
        self.assertEqual(account.metadata_json["douyin_challenge_count"], 1)
        self.assertEqual(account.metadata_json["douyin_challenge_recommended_next_action"], "complete_challenge_in_browser_profile")
        service.build_fetch_client.assert_not_called()

    def test_browser_validation_requires_profile_when_legacy_http_fallback_is_disabled(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="ua-1",
            proxy_url=None,
            headers_json=None,
            metadata_json={},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="session_reachable",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            warning_summary_json=None,
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._validate_with_live_browser_context = Mock(return_value=None)  # type: ignore[method-assign]
        service.build_fetch_client = Mock()  # type: ignore[method-assign]

        with patch("src.services.douyin_account_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "browser_profile_required")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.INVALID)
        self.assertEqual(account.last_error_code, "browser_profile_required")
        service.build_fetch_client.assert_not_called()

    def test_validate_blocks_normal_action_during_active_challenge_cooldown(self) -> None:
        account_id = uuid4()
        cooldown_until = datetime.now(UTC) + timedelta(minutes=5)
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=None,
            user_agent=None,
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "douyin_challenge_state": "challenge_repeat_limit_reached",
                "douyin_challenge_detected": True,
                "douyin_challenge_category": "challenge_required",
                "douyin_challenge_count": 3,
                "douyin_challenge_cooldown_until": cooldown_until.isoformat(),
                "douyin_challenge_recommended_next_action": "wait_then_complete_challenge_in_browser_profile",
            },
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=None,
            last_validation_status="challenge_repeat_limit_reached",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="browser_validation_challenge_required",
            last_error_message="browser_context_blocked_response",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_repeat_limit_reached"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._validate_with_live_browser_context = Mock(return_value=(True, "browser_validation_success"))  # type: ignore[method-assign]

        validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "challenge_cooldown_active")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.BLOCKED)
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.BLOCKED)
        self.assertEqual(account.warning_summary_json["reason"], "challenge_cooldown_active")
        self.assertEqual(account.warning_summary_json["challenge_state"], "challenge_cooldown_active")
        self.assertEqual(account.last_validation_status, "challenge_cooldown_active")
        self.assertEqual(account.last_error_code, "challenge_cooldown_active")
        self.assertEqual(account.metadata_json["douyin_challenge_state"], "challenge_repeat_limit_reached")
        self.assertEqual(account.metadata_json["douyin_challenge_recommended_next_action"], "wait_or_mark_challenge_solved_after_manual_completion")
        service._validate_with_live_browser_context.assert_not_called()

    def test_to_response_projects_active_cooldown_as_effective_challenge_state(self) -> None:
        account_id = uuid4()
        cooldown_until = datetime.now(UTC) + timedelta(minutes=5)
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            display_name="Cooldown account",
            douyin_user_id=None,
            status=DouyinAccountConnectionStatus.BLOCKED,
            is_default=False,
            session_secret_blob=None,
            user_agent=None,
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "douyin_challenge_state": "challenge_repeat_limit_reached",
                "douyin_challenge_detected": True,
                "douyin_challenge_category": "challenge_required",
                "douyin_challenge_count": 3,
                "douyin_challenge_cooldown_until": cooldown_until.isoformat(),
                "douyin_challenge_recommended_next_action": "wait_or_mark_challenge_solved_after_manual_completion",
                "last_browser_validation_managed_runtime_status": "managed_runtime_active",
                "last_browser_validation_runtime_attach_status": "live_runtime_attached",
                "last_browser_validation_page_recovery_status": "live_runtime_attached",
            },
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=None,
            last_validation_status="challenge_cooldown_active",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="challenge_cooldown_active",
            last_error_message="Douyin challenge cooldown is active.",
            warning_summary_json={"reason": "challenge_cooldown_active"},
            notes=None,
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )
        service = DouyinAccountService(Mock())

        with patch("src.services.douyin_account_service.douyin_browser_context_registry") as registry:
            registry.summary_for_account.return_value = SimpleNamespace(
                status="active",
                runtime_context_id="runtime-1",
                last_used_at=datetime(2026, 4, 24, tzinfo=UTC),
            )
            response = service.to_response(account)

        self.assertEqual(response.account_health_label, "Challenge cooldown active")
        self.assertEqual(response.browser_health_alignment.challenge_state, "challenge_cooldown_active")
        self.assertEqual(response.browser_health_alignment.automated_browser_validation_state, "challenge_cooldown_active")
        self.assertEqual(response.browser_health_alignment.challenge_repeat_limit_reached, True)
        self.assertIn("managed runtime can be healthy", response.browser_health_alignment.operator_detail)

    def test_browser_validation_uses_detached_http_only_when_legacy_http_fallback_enabled(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="ua-1",
            proxy_url=None,
            headers_json=None,
            metadata_json={},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="session_reachable",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            warning_summary_json=None,
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._validate_with_live_browser_context = Mock(return_value=None)  # type: ignore[method-assign]
        client = Mock()
        client.fetch_html.return_value = "<html><body>douyin video profile render_data</body></html>"
        service.build_fetch_client = Mock(return_value=client)  # type: ignore[method-assign]

        with patch("src.services.douyin_account_service.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_enable_legacy_http_fallback=True,
                douyin_reuse_live_browser_for_fetch=False,
                douyin_user_agent="ua-default",
                douyin_proxy_url=None,
            )
            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertTrue(valid)
        self.assertEqual(reason, "session_reachable")
        service.build_fetch_client.assert_called_once()
        client.fetch_html.assert_called_once()

    def test_mark_challenge_solved_runs_post_solve_recheck_and_keeps_intake_blocked_when_challenge_remains(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=None,
            user_agent=None,
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "douyin_challenge_state": "challenge_waiting_for_manual_verification",
                "douyin_challenge_detected": True,
                "douyin_challenge_category": "challenge_required",
                "douyin_challenge_count": 1,
                "douyin_challenge_recommended_next_action": "complete_challenge_in_browser_profile",
            },
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=None,
            last_validation_status="challenge_waiting_for_manual_verification",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="browser_validation_challenge_required",
            last_error_message="browser_context_blocked_response",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_waiting_for_manual_verification"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        def validate_still_blocked(account_id, *, validation_url=None, validation_source="manual_validate"):
            account.status = DouyinAccountConnectionStatus.INVALID
            account.last_validation_status = "browser_validation_challenge_required"
            account.last_error_code = "browser_validation_challenge_required"
            account.last_error_message = "browser_context_blocked_response"
            return account, False, "browser_validation_challenge_required"

        service.validate_account = Mock(side_effect=validate_still_blocked)  # type: ignore[method-assign]

        with patch("src.services.douyin_account_service.douyin_browser_context_registry") as registry:
            registry.summary_for_account.return_value = SimpleNamespace(runtime_context_id="runtime-1")
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.profile_identity_matches.return_value = True

            result = service.mark_challenge_solved(account_id)
            preflight = service.preflight_fetch_readiness(account_id)

        self.assertIs(result.account, account)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "browser_validation_challenge_required")
        self.assertEqual(result.post_check_result, "challenge_postcheck_still_required")
        self.assertEqual(account.metadata_json["douyin_challenge_state"], "challenge_cooldown")
        self.assertEqual(account.metadata_json["douyin_challenge_recommended_next_action"], "wait_then_complete_challenge_in_browser_profile")
        self.assertEqual(account.metadata_json["douyin_challenge_count"], 2)
        self.assertIn("douyin_challenge_cooldown_until", account.metadata_json)
        self.assertFalse(account.metadata_json["douyin_challenge_recheck_resolved"])
        self.assertFalse(account.metadata_json["douyin_challenge_intake_ready_after_recheck"])
        self.assertEqual(preflight.preflight_result, "failed")
        self.assertEqual(preflight.fetch_readiness_category, "fetch_blocked_by_browser_challenge")
        self.assertEqual(preflight.challenge_state, "challenge_cooldown_active")
        self.assertEqual(preflight.challenge_recommended_next_action, "wait_or_mark_challenge_solved_after_manual_completion")
        service.validate_account.assert_called_once_with(account_id, validation_url=None, validation_source="mark_challenge_solved")

    def test_recheck_challenge_success_clears_unresolved_challenge_metadata(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="browser-agent",
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "douyin_challenge_state": "challenge_recently_solved_pending_recheck",
                "douyin_challenge_detected": True,
                "douyin_challenge_category": "challenge_required",
                "douyin_challenge_count": 1,
                "douyin_challenge_last_solved_at": datetime(2026, 4, 24, tzinfo=UTC).isoformat(),
                "douyin_challenge_recheck_resolved": False,
                "douyin_challenge_recommended_next_action": "retry_browser_validation_after_manual_solve",
            },
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=None,
            last_validation_status="challenge_recently_solved_pending_recheck",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="challenge_recheck_required",
            last_error_message="Operator marked the Douyin challenge solved; browser-backed validation must pass before Intake can resume.",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_recently_solved_pending_recheck"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        def validate_success(account_id, *, validation_url=None, validation_source="manual_validate"):
            account.status = DouyinAccountConnectionStatus.ACTIVE
            account.last_validation_status = "browser_validation_success"
            account.last_error_code = None
            account.last_error_message = None
            account.last_successful_validation_at = datetime(2026, 4, 24, 20, 30, tzinfo=UTC)
            return account, True, "browser_validation_success"

        service.validate_account = Mock(side_effect=validate_success)  # type: ignore[method-assign]

        with patch("src.services.douyin_account_service.douyin_browser_context_registry") as registry:
            registry.summary_for_account.return_value = SimpleNamespace(runtime_context_id="runtime-1")
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.profile_identity_matches.return_value = True

            result = service.recheck_challenge_after_solve(account_id)

        self.assertIs(result.account, account)
        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "browser_validation_success")
        self.assertEqual(result.post_check_result, "challenge_postcheck_success")
        self.assertTrue(result.same_profile_reused)
        self.assertTrue(result.intake_ready_after_recheck)
        self.assertNotIn("douyin_challenge_state", account.metadata_json)
        self.assertNotIn("douyin_challenge_detected", account.metadata_json)
        self.assertNotIn("douyin_challenge_count", account.metadata_json)
        self.assertTrue(account.metadata_json["douyin_challenge_recheck_resolved"])
        self.assertEqual(account.metadata_json["douyin_challenge_same_runtime_reused"], True)
        self.assertEqual(account.metadata_json["douyin_challenge_same_profile_reused"], True)
        self.assertEqual(account.metadata_json["douyin_challenge_intake_ready_after_recheck"], True)
        self.assertEqual(account.last_validation_status, "browser_validation_success")
        service.validate_account.assert_called_once_with(account_id, validation_url=None, validation_source="challenge_recheck")

    def test_recheck_challenge_success_with_profile_mismatch_does_not_project_runtime_unavailable(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="browser-agent",
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "douyin_challenge_state": "challenge_recently_solved_pending_recheck",
                "douyin_challenge_detected": True,
                "douyin_challenge_category": "challenge_required",
                "douyin_challenge_count": 1,
                "douyin_challenge_last_solved_at": datetime(2026, 4, 24, tzinfo=UTC).isoformat(),
                "douyin_challenge_recheck_resolved": False,
                "douyin_challenge_recommended_next_action": "retry_browser_validation_after_manual_solve",
            },
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=None,
            last_validation_status="challenge_recently_solved_pending_recheck",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="challenge_recheck_required",
            last_error_message="Operator marked the Douyin challenge solved; browser-backed validation must pass before Intake can resume.",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_recently_solved_pending_recheck"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        def validate_success(account_id, *, validation_url=None, validation_source="manual_validate"):
            account.status = DouyinAccountConnectionStatus.ACTIVE
            account.last_validation_status = "browser_validation_success"
            account.last_error_code = None
            account.last_error_message = None
            account.last_successful_validation_at = datetime(2026, 4, 24, 20, 30, tzinfo=UTC)
            return account, True, "browser_validation_success"

        service.validate_account = Mock(side_effect=validate_success)  # type: ignore[method-assign]

        with patch("src.services.douyin_account_service.douyin_browser_context_registry") as registry:
            registry.summary_for_account.return_value = SimpleNamespace(runtime_context_id="runtime-1")
            registry.profile_identity_for_account.side_effect = [
                ("profile-1", "C:/profiles/profile-1"),
                ("profile-2", "C:/profiles/profile-2"),
            ]
            registry.profile_identity_matches.return_value = False

            result = service.recheck_challenge_after_solve(account_id)

        self.assertIs(result.account, account)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "runtime_rebind_profile_mismatch")
        self.assertEqual(result.post_check_result, "challenge_postcheck_profile_mismatch")
        self.assertNotEqual(result.post_check_result, "challenge_postcheck_runtime_unavailable")
        self.assertFalse(result.same_profile_reused)
        self.assertFalse(result.intake_ready_after_recheck)
        self.assertEqual(account.last_validation_status, "runtime_rebind_profile_mismatch")
        self.assertEqual(account.last_error_code, "browser_validation_profile_mismatch")
        self.assertEqual(account.metadata_json["douyin_challenge_postcheck_result"], "challenge_postcheck_profile_mismatch")
        self.assertEqual(account.metadata_json["douyin_challenge_state"], "challenge_waiting_for_manual_verification")
        self.assertEqual(account.metadata_json["douyin_challenge_recommended_next_action"], "reopen_saved_browser_profile_then_retry_recheck")
        service.validate_account.assert_called_once_with(account_id, validation_url=None, validation_source="challenge_recheck")

    def test_challenge_postcheck_result_projects_active_cooldown_explicitly(self) -> None:
        service = DouyinAccountService(Mock())

        self.assertEqual(
            service._challenge_postcheck_result_for(reason="challenge_cooldown_active", valid=False),
            "challenge_postcheck_cooldown_active",
        )

    def test_clear_challenge_state_for_revalidation_clears_cooldown_without_marking_ready(self) -> None:
        account_id = uuid4()
        now = datetime(2026, 4, 24, tzinfo=UTC)
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.BLOCKED,
            session_secret_blob=None,
            user_agent="browser-agent",
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "douyin_challenge_state": "challenge_cooldown",
                "douyin_challenge_cooldown_until": (now + timedelta(minutes=10)).isoformat(),
                "douyin_challenge_detected": True,
                "douyin_challenge_category": "challenge_required",
                "douyin_challenge_count": 2,
                "douyin_challenge_recommended_next_action": "wait_or_mark_challenge_solved_after_manual_completion",
                "browser_context_blocked_count": 3,
                "douyin_profile_quarantine_state": "quarantined",
            },
            last_validated_at=now,
            last_successful_validation_at=None,
            last_validation_status="challenge_cooldown_active",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="challenge_cooldown_active",
            last_error_message="cooldown active",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_cooldown_active"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        cleared = service.clear_challenge_state_for_revalidation(account_id)

        self.assertIs(cleared, account)
        self.assertEqual(account.status, DouyinAccountConnectionStatus.INVALID)
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.UNKNOWN)
        self.assertEqual(account.last_validation_status, "manual_revalidation_required")
        self.assertEqual(account.last_error_code, "manual_revalidation_required")
        self.assertNotIn("douyin_challenge_state", account.metadata_json)
        self.assertNotIn("douyin_challenge_cooldown_until", account.metadata_json)
        self.assertNotIn("browser_context_blocked_count", account.metadata_json)
        self.assertNotIn("douyin_profile_quarantine_state", account.metadata_json)
        self.assertTrue(account.metadata_json["manual_challenge_clear_requires_revalidate"])

    def test_clear_challenge_state_removes_stale_cooldown_preflight_block(self) -> None:
        account_id = uuid4()
        now = datetime(2026, 4, 24, tzinfo=UTC)
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.BLOCKED,
            session_secret_blob=None,
            user_agent="browser-agent",
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "douyin_challenge_state": "challenge_cooldown",
                "douyin_challenge_cooldown_until": (now + timedelta(minutes=10)).isoformat(),
                "douyin_challenge_detected": True,
            },
            last_validated_at=now,
            last_successful_validation_at=None,
            last_validation_status="challenge_cooldown_active",
            validation_source="manual_validate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="challenge_cooldown_active",
            last_error_message="cooldown active",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_cooldown_active"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        service.clear_challenge_state_for_revalidation(account_id)
        with patch("src.services.douyin_account_service.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                douyin_prefer_browser_profile_for_fetch=True,
                douyin_enable_legacy_http_fallback=False,
                douyin_intake_preflight_cache_ttl_seconds=0,
            )
            preflight = service.preflight_fetch_readiness(account_id)

        self.assertEqual(preflight.preflight_failure_code, "account_not_fetch_ready")
        self.assertNotEqual(preflight.challenge_state, "challenge_cooldown_active")

    def test_operator_confirm_ready_clears_stale_inconclusive_state_without_claiming_automated_ready(self) -> None:
        account_id = uuid4()
        now = datetime(2026, 4, 24, tzinfo=UTC)
        account = SimpleNamespace(
            id=account_id,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "douyin_challenge_state": "challenge_cooldown",
                "douyin_challenge_cooldown_until": (now + timedelta(minutes=10)).isoformat(),
                "last_browser_validation_category": "browser_validation_inconclusive",
                "last_browser_validation_final_category": "browser_validation_inconclusive",
                "browser_context_blocked_count": 2,
            },
            status=DouyinAccountConnectionStatus.INVALID,
            health_status=DouyinAccountHealthStatus.UNKNOWN,
            warning_level=DouyinAccountWarningLevel.WARN,
            last_validated_at=now,
            last_successful_validation_at=None,
            last_validation_status="browser_validation_inconclusive",
            validation_source="readiness_revalidate",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="browser_validation_inconclusive",
            last_error_message="browser_prevalidation_navigation_uncertain",
            warning_summary_json={"reason": "browser_validation_inconclusive"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        confirmed = service.operator_confirm_ready(account_id)

        self.assertIs(confirmed, account)
        self.assertEqual(account.status, DouyinAccountConnectionStatus.INVALID)
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.UNKNOWN)
        self.assertEqual(account.last_validation_status, "operator_confirmed_ready")
        self.assertEqual(account.last_error_code, "operator_confirmed_ready")
        self.assertIn("operator_confirmed_ready_at", account.metadata_json)
        self.assertNotIn("douyin_challenge_state", account.metadata_json)
        self.assertNotIn("douyin_challenge_cooldown_until", account.metadata_json)
        self.assertNotIn("last_browser_validation_category", account.metadata_json)

    def test_operator_confirm_ready_preflight_allows_browser_profile_within_ttl(self) -> None:
        account_id = uuid4()
        now = datetime.now(UTC)
        account = SimpleNamespace(
            id=account_id,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "operator_confirmed_ready_at": now.isoformat(),
            },
            status=DouyinAccountConnectionStatus.INVALID,
            health_status=DouyinAccountHealthStatus.UNKNOWN,
            warning_level=DouyinAccountWarningLevel.WARN,
            last_validated_at=now,
            last_successful_validation_at=None,
            last_validation_status="operator_confirmed_ready",
            validation_source="operator_command",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="operator_confirmed_ready",
            last_error_message="manual confirmation only",
            warning_summary_json={"reason": "operator_confirmed_ready"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        with patch("src.services.douyin_account_service.douyin_browser_context_registry") as registry:
            registry.summary_for_account.return_value = SimpleNamespace(
                status="none",
                managed_runtime_status="managed_runtime_missing",
                profile_conflict_status=None,
            )
            preflight = service.preflight_fetch_readiness(account_id)

        self.assertEqual(preflight.preflight_result, "passed")
        self.assertEqual(preflight.fetch_readiness_category, "fetch_ready_operator_confirmed")
        self.assertEqual(preflight.selected_fetch_path, "browser_profile")

    def test_operator_confirm_ready_preflight_rejects_expired_confirmation(self) -> None:
        account_id = uuid4()
        now = datetime.now(UTC)
        account = SimpleNamespace(
            id=account_id,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "operator_confirmed_ready_at": (now - timedelta(hours=7)).isoformat(),
            },
            status=DouyinAccountConnectionStatus.INVALID,
            health_status=DouyinAccountHealthStatus.UNKNOWN,
            warning_level=DouyinAccountWarningLevel.WARN,
            last_validated_at=now,
            last_successful_validation_at=None,
            last_validation_status="operator_confirmed_ready",
            validation_source="operator_command",
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="operator_confirmed_ready",
            last_error_message="manual confirmation only",
            warning_summary_json={"reason": "operator_confirmed_ready"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)

        preflight = service.preflight_fetch_readiness(account_id)

        self.assertEqual(preflight.preflight_result, "failed")
        self.assertEqual(preflight.preflight_failure_code, "account_not_fetch_ready")

    def test_browser_validation_attempt_reset_removes_stale_reopen_diagnostics(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=None,
            user_agent=None,
            proxy_url=None,
            headers_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "browser_profile_path": "C:/profiles/profile-1",
                "last_browser_validation_auto_reopen_attempted": True,
                "last_browser_validation_reopen_status": "failed",
                "last_browser_validation_reopen_reason": "persistent_profile_open_failed:NotImplementedError",
                "last_browser_validation_runtime_reattached": False,
                "last_browser_validation_continued_after_reopen": False,
                "last_browser_validation_final_category": "profile_reopen_failed",
            },
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="profile_reopen_failed",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="browser_validation_runtime_unavailable",
            last_error_message="persistent_profile_open_failed:NotImplementedError",
            health_status=DouyinAccountHealthStatus.INVALID,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "profile_reopen_failed"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        service._ensure_persistent_profile_context = Mock()  # type: ignore[method-assign]
        browser_result = SimpleNamespace(
            status="blocked",
            reason="browser_context_blocked_response",
            cookie_header="sessionid=abc; sid_guard=xyz",
            user_agent="browser-agent",
            runtime_context_id="runtime-1",
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(douyin_reuse_live_browser_for_validation=True)
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.validate_account_context.return_value = browser_result

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "browser_validation_challenge_required")
        self.assertEqual(account.metadata_json["last_browser_validation_auto_reopen_attempted"], False)
        self.assertNotIn("last_browser_validation_reopen_status", account.metadata_json)
        self.assertNotIn("last_browser_validation_reopen_reason", account.metadata_json)
        self.assertFalse(account.metadata_json["last_browser_validation_runtime_reattached"])
        self.assertFalse(account.metadata_json["last_browser_validation_continued_after_reopen"])
        self.assertEqual(account.metadata_json["last_browser_validation_final_category"], "browser_validation_challenge_required")
        self.assertEqual(account.metadata_json["last_browser_validation_challenge_category"], "challenge_required")
        self.assertIsInstance(account.metadata_json["last_browser_validation_attempt_id"], str)

        summary = service._browser_health_alignment_summary(
            account,
            browser_context_status="active",
            browser_context_available=True,
            has_saved_profile=True,
        )
        self.assertFalse(summary.auto_reopen_attempted)
        self.assertFalse(summary.runtime_reattached)
        self.assertFalse(summary.validation_continued_after_reopen)
        self.assertIsNone(summary.auto_reopen_status)
        self.assertEqual(summary.automated_browser_validation_state, "challenge_required")
        self.assertEqual(summary.final_validation_category, "browser_validation_challenge_required")
        self.assertEqual(summary.challenge_category, "challenge_required")
        self.assertEqual(summary.recommended_next_action, "complete_challenge_in_browser_profile")

    def test_validate_auto_reopens_saved_profile_when_live_context_missing_then_continues_validation(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=None,
            user_agent="saved-agent",
            proxy_url=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="browser_validation_runtime_unavailable",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="browser_validation_runtime_unavailable",
            last_error_message="no_live_browser_context",
            health_status=DouyinAccountHealthStatus.UNKNOWN,
            warning_level=DouyinAccountWarningLevel.WARN,
            warning_summary_json={"reason": "browser_validation_runtime_unavailable"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        no_live_result = SimpleNamespace(
            status="none",
            reason="no_live_browser_context",
            cookie_header=None,
            user_agent=None,
            runtime_context_id=None,
            runtime_attach_status="runtime_missing_reopen_required",
            page_recovery_status=None,
        )
        passed_result = SimpleNamespace(
            status="passed",
            reason="authenticated_context_reachable_after_reopen",
            cookie_header="sessionid=abc; sid_guard=xyz",
            user_agent="browser-agent",
            runtime_context_id="runtime-1",
            runtime_attach_status="live_runtime_attached",
            page_recovery_status="live_runtime_attached",
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(
                douyin_reuse_live_browser_for_validation=True,
                douyin_prefer_browser_profile_for_validation=False,
            )
            registry.validate_account_context.side_effect = [no_live_result, passed_result]
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.open_profile_for_account.return_value = SimpleNamespace(
                status="active",
                runtime_context_id="runtime-1",
                reason="persistent_profile_reopened",
                account_connection_id=account_id,
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
            )
            registry.profile_identity_matches.return_value = True
            registry.summary_for_account.return_value = SimpleNamespace(
                status="active",
                reason="active",
                runtime_context_id="runtime-1",
            )

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertTrue(valid)
        self.assertEqual(reason, "browser_validation_success")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.ACTIVE)
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.HEALTHY)
        self.assertEqual(account.warning_level, DouyinAccountWarningLevel.NONE)
        self.assertIsNone(account.last_error_code)
        self.assertIsNone(account.last_error_message)
        self.assertEqual(account.metadata_json["last_browser_validation_reopen_status"], "reopen_success")
        self.assertEqual(account.metadata_json["last_browser_validation_reopen_reason"], "persistent_profile_reopened")
        self.assertTrue(account.metadata_json["last_browser_validation_runtime_reattached"])
        self.assertTrue(account.metadata_json["last_browser_validation_continued_after_reopen"])
        self.assertEqual(account.metadata_json["last_browser_validation_category"], "browser_validation_success")
        self.assertEqual(account.metadata_json["last_browser_validation_final_category"], "browser_validation_success")
        self.assertEqual(service._decode_session_cookie(account.session_secret_blob), "sessionid=abc; sid_guard=xyz")
        self.assertEqual(registry.validate_account_context.call_count, 2)
        registry.open_profile_for_account.assert_called_once_with(
            workspace_id=account.workspace_id,
            account_connection_id=account.id,
            browser_profile_id="profile-1",
            browser_profile_path="C:/profiles/profile-1",
            user_agent="saved-agent",
            proxy_url=None,
        )

    def test_validate_uses_existing_live_runtime_without_reopening_saved_profile(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.INVALID,
            session_secret_blob=None,
            user_agent="saved-agent",
            proxy_url=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="challenge_waiting_for_manual_verification",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code="browser_validation_challenge_required",
            last_error_message="browser_context_blocked_response",
            health_status=DouyinAccountHealthStatus.BLOCKED,
            warning_level=DouyinAccountWarningLevel.BLOCK,
            warning_summary_json={"reason": "challenge_waiting_for_manual_verification"},
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        live_result = SimpleNamespace(
            status="passed",
            reason="authenticated_context_reachable",
            cookie_header="sessionid=abc; sid_guard=xyz",
            user_agent="browser-agent",
            runtime_context_id="runtime-live",
            runtime_attach_status="live_runtime_attached",
            page_recovery_status="live_context_page_reacquired",
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(
                douyin_reuse_live_browser_for_validation=True,
                douyin_prefer_browser_profile_for_validation=False,
            )
            registry.validate_account_context.return_value = live_result
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertTrue(valid)
        self.assertEqual(reason, "browser_validation_success")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.ACTIVE)
        self.assertEqual(account.metadata_json["last_browser_validation_runtime_attach_status"], "live_runtime_attached")
        self.assertEqual(account.metadata_json["last_browser_validation_page_recovery_status"], "live_context_page_reacquired")
        self.assertFalse(account.metadata_json["last_browser_validation_auto_reopen_attempted"])
        self.assertEqual(account.metadata_json["last_browser_validation_category"], "browser_validation_success")
        registry.validate_account_context.assert_called_once_with(account_id, validation_url="https://www.douyin.com/")
        registry.open_profile_for_account.assert_not_called()

    def test_validate_returns_runtime_unavailable_only_after_auto_reopen_fails(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=None,
            user_agent=None,
            proxy_url=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="browser_validation_success",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            warning_summary_json=None,
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        no_live_result = SimpleNamespace(
            status="none",
            reason="no_live_browser_context",
            cookie_header=None,
            user_agent=None,
            runtime_context_id=None,
            runtime_attach_status="runtime_missing_reopen_required",
            page_recovery_status=None,
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(
                douyin_reuse_live_browser_for_validation=True,
                douyin_prefer_browser_profile_for_validation=False,
            )
            registry.validate_account_context.return_value = no_live_result
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.open_profile_for_account.return_value = SimpleNamespace(
                status="invalid",
                runtime_context_id=None,
                reason="persistent_profile_open_failed:Error",
                managed_runtime_status="managed_runtime_missing",
                profile_conflict_status=None,
            )

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "profile_reopen_failed")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.INVALID)
        self.assertEqual(account.last_validation_status, "profile_reopen_failed")
        self.assertEqual(account.last_error_code, "browser_validation_runtime_unavailable")
        self.assertEqual(account.last_error_message, "persistent_profile_open_failed:Error")
        self.assertEqual(account.health_status, DouyinAccountHealthStatus.INVALID)
        self.assertEqual(account.warning_level, DouyinAccountWarningLevel.BLOCK)
        self.assertEqual(account.metadata_json["last_browser_profile_open_status"], "invalid")
        self.assertEqual(account.metadata_json["last_browser_validation_reopen_status"], "failed")
        self.assertEqual(account.metadata_json["last_browser_validation_managed_runtime_status"], "managed_runtime_missing")
        self.assertIsNone(account.metadata_json["last_browser_validation_profile_conflict_status"])
        self.assertEqual(account.metadata_json["last_browser_validation_final_category"], "profile_reopen_failed")
        self.assertEqual(registry.validate_account_context.call_count, 1)
        registry.open_profile_for_account.assert_called_once()

    def test_validate_classifies_external_profile_lock_conflict_after_auto_reopen_fails(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=None,
            user_agent=None,
            proxy_url=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="browser_validation_success",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            warning_summary_json=None,
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        no_live_result = SimpleNamespace(
            status="none",
            reason="no_live_browser_context",
            cookie_header=None,
            user_agent=None,
            runtime_context_id=None,
            runtime_attach_status="runtime_missing_reopen_required",
            page_recovery_status=None,
            managed_runtime_status="managed_runtime_missing",
            profile_conflict_status=None,
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(
                douyin_reuse_live_browser_for_validation=True,
                douyin_prefer_browser_profile_for_validation=False,
            )
            registry.validate_account_context.return_value = no_live_result
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.open_profile_for_account.return_value = SimpleNamespace(
                status="invalid",
                runtime_context_id=None,
                reason="profile_locked_by_existing_process:ProcessSingleton",
                managed_runtime_status="profile_opened_outside_managed_runtime",
                profile_conflict_status="profile_opened_outside_managed_runtime",
            )

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "profile_reopen_failed")
        self.assertEqual(account.last_validation_status, "profile_reopen_failed")
        self.assertEqual(account.last_error_code, "browser_validation_runtime_unavailable")
        self.assertEqual(account.last_error_message, "profile_locked_by_existing_process:ProcessSingleton")
        self.assertEqual(account.metadata_json["last_browser_profile_open_profile_conflict_status"], "profile_opened_outside_managed_runtime")
        self.assertEqual(account.metadata_json["last_browser_validation_managed_runtime_status"], "profile_opened_outside_managed_runtime")
        self.assertEqual(account.metadata_json["last_browser_validation_profile_conflict_status"], "profile_opened_outside_managed_runtime")
        summary = service._browser_health_alignment_summary(
            account,
            browser_context_status="invalid",
            browser_context_available=False,
            has_saved_profile=True,
        )
        self.assertEqual(summary.automated_browser_validation_state, "profile_opened_outside_managed_runtime")
        self.assertEqual(summary.profile_conflict_status, "profile_opened_outside_managed_runtime")
        self.assertIn("outside the app-managed runtime", summary.operator_summary)

    def test_validate_marks_runtime_attach_failed_when_reopened_profile_is_not_bound_to_account(self) -> None:
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=uuid4(),
            status=DouyinAccountConnectionStatus.ACTIVE,
            session_secret_blob=None,
            user_agent="saved-agent",
            proxy_url=None,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            last_validated_at=None,
            last_successful_validation_at=None,
            last_validation_status="browser_validation_success",
            validation_source=None,
            next_validation_due_at=None,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            warning_summary_json=None,
        )
        db = Mock()
        db.get.return_value = account
        service = DouyinAccountService(db)
        no_live_result = SimpleNamespace(
            status="none",
            reason="no_live_browser_context",
            cookie_header=None,
            user_agent=None,
            runtime_context_id=None,
            runtime_attach_status="runtime_missing_reopen_required",
            page_recovery_status=None,
        )

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(
                douyin_reuse_live_browser_for_validation=True,
                douyin_prefer_browser_profile_for_validation=False,
            )
            registry.validate_account_context.return_value = no_live_result
            registry.profile_identity_for_account.return_value = ("profile-1", "C:/profiles/profile-1")
            registry.open_profile_for_account.return_value = SimpleNamespace(
                status="active",
                runtime_context_id="runtime-wrong",
                reason="persistent_profile_reopened",
                account_connection_id=uuid4(),
                browser_profile_id="profile-1",
                browser_profile_path="C:/profiles/profile-1",
            )

            validated, valid, reason = service.validate_account(account_id)

        self.assertIs(validated, account)
        self.assertFalse(valid)
        self.assertEqual(reason, "runtime_attach_failed")
        self.assertEqual(account.last_validation_status, "runtime_attach_failed")
        self.assertEqual(account.last_error_code, "browser_validation_runtime_unavailable")
        self.assertEqual(account.last_error_message, "runtime_rebind_account_mismatch")
        self.assertEqual(account.metadata_json["last_browser_validation_reopen_status"], "reattach_failed")
        self.assertFalse(account.metadata_json["last_browser_validation_runtime_reattached"])
        self.assertFalse(account.metadata_json["last_browser_validation_continued_after_reopen"])
        self.assertEqual(account.metadata_json["last_browser_validation_final_category"], "runtime_attach_failed")
        self.assertEqual(registry.validate_account_context.call_count, 1)

    def test_to_response_exposes_auto_reopen_diagnostics(self) -> None:
        service = DouyinAccountService(Mock())
        account = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            display_name="Browser account",
            douyin_user_id="user-1",
            status=DouyinAccountConnectionStatus.ACTIVE,
            is_default=True,
            session_secret_blob=service._encode_session_cookie("sessionid=abc; sid_guard=xyz"),
            user_agent="ua-1",
            proxy_url=None,
            headers_json={"User-Agent": "ua-1"},
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_successful_validation_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_validation_status="browser_validation_success",
            validation_source="manual_validate",
            next_validation_due_at=datetime(2026, 4, 25, tzinfo=UTC),
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            warning_summary_json=None,
            metadata_json={
                "browser_profile_id": "profile-1",
                "last_browser_context_status": "passed",
                "last_browser_context_reason": "authenticated_context_reachable_after_reopen",
                "browser_context_checked_at": "2026-04-24T00:00:00+00:00",
                "last_browser_validation_auto_reopen_attempted": True,
                "last_browser_validation_reopen_status": "browser_validation_runtime_reopened",
                "last_browser_validation_runtime_reattached": True,
                "last_browser_validation_continued_after_reopen": True,
                "last_browser_validation_final_category": "browser_validation_success",
            },
            notes=None,
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )

        response = service.to_response(account)

        self.assertTrue(response.browser_health_alignment.auto_reopen_attempted)
        self.assertTrue(response.browser_health_alignment.auto_reopen_succeeded)
        self.assertEqual(response.browser_health_alignment.auto_reopen_status, "browser_validation_runtime_reopened")
        self.assertIsNone(response.browser_health_alignment.runtime_attach_status)
        self.assertIsNone(response.browser_health_alignment.page_recovery_status)
        self.assertTrue(response.browser_health_alignment.runtime_reattached)
        self.assertTrue(response.browser_health_alignment.validation_continued_after_reopen)
        self.assertEqual(response.browser_health_alignment.final_validation_category, "browser_validation_success")

    def test_validation_reopens_exact_saved_profile_identity_without_allocating_new_profile(self) -> None:
        account = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
            user_agent=None,
            proxy_url=None,
        )
        service = DouyinAccountService(Mock())

        with patch("src.services.douyin_account_service.get_settings") as get_settings, patch(
            "src.services.douyin_account_service.douyin_browser_context_registry"
        ) as registry:
            get_settings.return_value = SimpleNamespace(douyin_prefer_browser_profile_for_validation=True)
            registry.open_profile_for_account.return_value = SimpleNamespace(
                status="active",
                runtime_context_id="runtime-1",
                reason="reused",
            )

            service._ensure_persistent_profile_context(account, purpose="validation")

        registry.open_profile_for_account.assert_called_once_with(
            workspace_id=account.workspace_id,
            account_connection_id=account.id,
            browser_profile_id="profile-1",
            browser_profile_path="C:/profiles/profile-1",
            user_agent=None,
            proxy_url=None,
        )
        self.assertEqual(account.metadata_json["browser_context_id"], "runtime-1")
        self.assertEqual(account.metadata_json["last_browser_profile_open_status"], "active")

    def test_health_summary_marks_active_old_validation_as_stale(self) -> None:
        now = datetime(2026, 4, 22, tzinfo=UTC)
        account = SimpleNamespace(
            status=DouyinAccountConnectionStatus.ACTIVE,
            last_successful_validation_at=datetime(2026, 4, 20, tzinfo=UTC),
            last_validated_at=datetime(2026, 4, 20, tzinfo=UTC),
            next_validation_due_at=None,
            expires_at=None,
            last_validation_status="session_reachable",
        )
        service = DouyinAccountService(Mock())

        health = service.health_summary(account, now=now)

        self.assertEqual(health.health_status, DouyinAccountHealthStatus.STALE)
        self.assertTrue(health.can_use_for_live_fetch)

    def test_list_accounts_hides_soft_deleted_by_default(self) -> None:
        active = SimpleNamespace(metadata_json=None)
        deleted = SimpleNamespace(metadata_json={"delete_mode": "soft_delete"})
        db = Mock()
        db.scalars.return_value = [active, deleted]
        service = DouyinAccountService(db)

        accounts = service.list_accounts()

        self.assertEqual(accounts, [active])

    def test_delete_account_soft_deletes_and_preserves_row(self) -> None:
        now = datetime(2026, 4, 22, tzinfo=UTC)
        account_id = uuid4()
        workspace_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=workspace_id,
            display_name="Creator account",
            douyin_user_id=None,
            status=DouyinAccountConnectionStatus.ACTIVE,
            is_default=True,
            session_secret_blob=DouyinAccountService(Mock())._encode_session_cookie("sessionid=abc"),
            user_agent="agent",
            proxy_url=None,
            headers_json=None,
            health_status=DouyinAccountHealthStatus.HEALTHY,
            warning_level=DouyinAccountWarningLevel.NONE,
            last_validated_at=now,
            last_successful_validation_at=now,
            last_validation_status="session_reachable",
            validation_source="manual_validate",
            next_validation_due_at=now + DOUYIN_ACCOUNT_FRESH_WINDOW,
            expires_at=None,
            last_error_code=None,
            last_error_message=None,
            warning_summary_json=None,
            metadata_json=None,
            notes=None,
            created_at=now,
            updated_at=now,
        )
        db = Mock()
        db.get.return_value = account
        db.scalar.return_value = None
        db.scalars.return_value = []
        service = DouyinAccountService(db)

        result = service.delete_account(account_id)

        self.assertTrue(result.success)
        self.assertEqual(result.delete_mode, "soft_delete")
        self.assertEqual(account.status, DouyinAccountConnectionStatus.DISABLED)
        self.assertFalse(account.is_default)
        self.assertEqual(account.metadata_json["delete_mode"], "soft_delete")
        self.assertEqual(account.metadata_json["original_display_name"], "Creator account")
        self.assertIn("deleted_account_was_default", result.warnings)
        self.assertIn("deleted_account_was_only_usable_live_fetch_account", result.warnings)
        db.delete.assert_not_called()
        db.commit.assert_called_once()

    def test_health_summary_blocks_quarantined_saved_profile(self) -> None:
        account = SimpleNamespace(
            status=DouyinAccountConnectionStatus.ACTIVE,
            last_successful_validation_at=datetime(2026, 4, 24, tzinfo=UTC),
            last_validated_at=datetime(2026, 4, 24, tzinfo=UTC),
            next_validation_due_at=datetime(2026, 4, 24, tzinfo=UTC) + DOUYIN_ACCOUNT_FRESH_WINDOW,
            expires_at=None,
            last_validation_status="session_reachable",
            metadata_json={
                "browser_profile_id": "profile-1",
                "douyin_challenge_count": 3,
            },
        )
        service = DouyinAccountService(Mock())

        health = service.health_summary(account, now=datetime(2026, 4, 24, tzinfo=UTC))

        self.assertEqual(health.health_status, DouyinAccountHealthStatus.BLOCKED)
        self.assertEqual(health.warning_level, DouyinAccountWarningLevel.BLOCK)
        self.assertFalse(health.can_use_for_live_fetch)
        self.assertEqual(health.warning_summary["profile_quarantine_state"], "quarantined")
        self.assertEqual(health.warning_summary["reason"], "challenge_count_threshold_reached")
        self.assertEqual(health.warning_summary["profile_quarantine_recommended_next_action"], "create_clean_managed_browser_profile")

    def test_quarantine_detection_requires_saved_browser_profile_metadata(self) -> None:
        metadata = {"douyin_challenge_count": 3, "browser_context_blocked_count": 3}
        service = DouyinAccountService(Mock())

        service._maybe_apply_profile_quarantine(metadata, now=datetime(2026, 4, 24, tzinfo=UTC))

        self.assertNotIn("douyin_profile_quarantine_state", metadata)
        self.assertEqual(service._profile_quarantine_state(metadata), "active_preferred")
        self.assertFalse(service._profile_quarantine_blocks_primary_flow(metadata))

    def test_connect_time_browser_context_block_is_retryable(self) -> None:
        service = DouyinAccountService(Mock())

        self.assertTrue(service._is_retryable_browser_connect_validation_block("connect_time", 1))
        self.assertTrue(service._is_retryable_browser_connect_validation_block("connect_retry", 1))
        self.assertFalse(service._is_retryable_browser_connect_validation_block("connect_retry", 2))
        self.assertFalse(service._is_retryable_browser_connect_validation_block("manual_validate", 1))


if __name__ == "__main__":
    unittest.main()
