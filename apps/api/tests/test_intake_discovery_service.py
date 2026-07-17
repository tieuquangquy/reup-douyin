from types import SimpleNamespace
from datetime import UTC, datetime
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.adapters.types import IngestSummary
from src.enums import CrawlSessionStatus, SourcePlatformEnum
from src.adapters.errors import SourceAdapterErrorCode
from src.services.intake_discovery_service import ExistingProfileUsability, IntakeDiscoveryError, IntakeDiscoveryService
from src.services.source_ingest_service import SourceIngestError


PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid"


def candidate_result(total: int = 2, matched: int = 1):
    return SimpleNamespace(
        total_count=total,
        matched_count=matched,
        rejected_count=total - matched,
        evaluations=[object()] * matched,
    )


def ingest_summary(source_profile_id):
    return IngestSummary(
        crawl_session_id=str(uuid4()),
        status=CrawlSessionStatus.COMPLETED,
        source_profile_id=str(source_profile_id),
        source_platform=SourcePlatformEnum.DOUYIN,
        submitted_profile_url=PROFILE_URL,
        normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
        videos_discovered_count=3,
        videos_created_count=3,
        videos_updated_count=0,
        snapshots_created_count=3,
    )


def preflight_result(
    *,
    result: str = "passed",
    category: str = "fetch_ready_browser_profile",
    path: str = "browser_profile",
    reopen_attempted: bool = False,
    reopen_result: str | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    cached: bool = False,
    watchdog_result: str | None = "healthy",
    watchdog_status: str | None = "active",
    runtime_reconciled: bool = False,
    challenge_state: str | None = None,
    challenge_category: str | None = None,
    challenge_count: int | None = None,
    challenge_cooldown_until=None,
    challenge_recommended_next_action: str | None = None,
    managed_runtime_status: str | None = None,
    profile_conflict_status: str | None = None,
    profile_quarantine_state: str = "active_preferred",
    profile_quarantine_reason: str | None = None,
    profile_quarantine_detected: bool = False,
    profile_quarantine_recommended_next_action: str | None = None,
    profile_quarantine_blocks_primary_flow: bool = False,
    profile_quarantine_replaced_by_account_id=None,
    profile_quarantine_clean_profile_recommendation: str | None = None,
):
    return SimpleNamespace(
        preflight_ran=True,
        preflight_result=result,
        fetch_readiness_category=category,
        selected_fetch_path=path,
        browser_profile_available=path == "browser_profile",
        browser_reopen_attempted=reopen_attempted,
        browser_reopen_result=reopen_result,
        browser_context_status="active" if path == "browser_profile" else "none",
        browser_context_reason=None,
        managed_runtime_status=managed_runtime_status,
        profile_conflict_status=profile_conflict_status,
        preflight_failure_code=failure_code,
        preflight_failure_message=failure_message,
        preflight_cached=cached,
        watchdog_result=watchdog_result,
        watchdog_status=watchdog_status,
        watchdog_reason=None,
        runtime_reconciled=runtime_reconciled,
        challenge_state=challenge_state,
        challenge_category=challenge_category,
        challenge_count=challenge_count,
        challenge_cooldown_until=challenge_cooldown_until,
        challenge_recommended_next_action=challenge_recommended_next_action,
        profile_quarantine_state=profile_quarantine_state,
        profile_quarantine_reason=profile_quarantine_reason,
        profile_quarantine_detected=profile_quarantine_detected,
        profile_quarantine_recommended_next_action=profile_quarantine_recommended_next_action,
        profile_quarantine_blocks_primary_flow=profile_quarantine_blocks_primary_flow,
        profile_quarantine_replaced_by_account_id=profile_quarantine_replaced_by_account_id,
        profile_quarantine_clean_profile_recommendation=profile_quarantine_clean_profile_recommendation,
        to_dict=lambda: {
            "preflight_ran": True,
            "preflight_result": result,
            "fetch_readiness_category": category,
            "selected_fetch_path": path,
            "browser_profile_available": path == "browser_profile",
            "browser_reopen_attempted": reopen_attempted,
            "browser_reopen_result": reopen_result,
            "managed_runtime_status": managed_runtime_status,
            "profile_conflict_status": profile_conflict_status,
            "preflight_failure_code": failure_code,
            "preflight_failure_message": failure_message,
            "preflight_cached": cached,
            "watchdog_result": watchdog_result,
            "watchdog_status": watchdog_status,
            "watchdog_reason": None,
            "runtime_reconciled": runtime_reconciled,
            "challenge_state": challenge_state,
            "challenge_category": challenge_category,
            "challenge_count": challenge_count,
            "challenge_cooldown_until": challenge_cooldown_until,
            "challenge_recommended_next_action": challenge_recommended_next_action,
            "profile_quarantine_state": profile_quarantine_state,
            "profile_quarantine_reason": profile_quarantine_reason,
            "profile_quarantine_detected": profile_quarantine_detected,
            "profile_quarantine_recommended_next_action": profile_quarantine_recommended_next_action,
            "profile_quarantine_blocks_primary_flow": profile_quarantine_blocks_primary_flow,
            "profile_quarantine_replaced_by_account_id": profile_quarantine_replaced_by_account_id,
            "profile_quarantine_clean_profile_recommendation": profile_quarantine_clean_profile_recommendation,
        },
    )


class IntakeDiscoveryServiceTests(unittest.TestCase):
    def test_ready_check_reports_ready_for_browser_profile(self) -> None:
        resolved_account_id = uuid4()
        resolved_account = SimpleNamespace(id=resolved_account_id, display_name="Healthy browser account")
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=resolved_account_id,
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        account_service = Mock()
        account_service.get_account.side_effect = lambda account_id: resolved_account if account_id == resolved_account_id else None
        account_service.health_summary.return_value = SimpleNamespace(health_status="HEALTHY", can_use_for_live_fetch=True)
        account_service.preflight_fetch_readiness.return_value = preflight_result()

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
                summary = service.ready_check(workspace_id=None, requested_account_id=None, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "READY")
        self.assertTrue(summary.safe_to_run_intake_now)
        self.assertEqual(summary.intended_fetch_path, "browser_profile")
        self.assertEqual(summary.resolved_account_label, "Healthy browser account")
        self.assertEqual(summary.recommended_action, "run_intake_now")

    def test_ready_check_blocks_http_fallback_ready_by_default(self) -> None:
        resolved_account_id = uuid4()
        selected_account_id = uuid4()
        resolved_account = SimpleNamespace(id=resolved_account_id, display_name="Fallback account")
        selected_account = SimpleNamespace(id=selected_account_id, display_name="Selected account")
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=selected_account_id,
                resolved_account_id=resolved_account_id,
                selection_mode="fallback",
                selection_reason="selected_account_unusable",
                fallback_notice="Used fallback account",
            )
        )

        account_service = Mock()
        account_service.get_account.side_effect = lambda account_id: (
            selected_account if account_id == selected_account_id else resolved_account if account_id == resolved_account_id else None
        )
        account_service.health_summary.return_value = SimpleNamespace(health_status="STALE", can_use_for_live_fetch=True)
        account_service.preflight_fetch_readiness.return_value = preflight_result(
            category="fetch_ready_http_fallback",
            path="http_html",
            watchdog_result="missing",
            watchdog_status="none",
        )

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
                summary = service.ready_check(workspace_id=None, requested_account_id=selected_account_id, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "FALLBACK_READY")
        self.assertFalse(summary.safe_to_run_intake_now)
        self.assertEqual(summary.selected_account_label, "Selected account")
        self.assertEqual(summary.resolved_account_label, "Fallback account")
        self.assertEqual(summary.intended_fetch_path, "http_html")
        self.assertFalse(summary.fallback_allowed)
        self.assertEqual(summary.recommended_action, "go_to_accounts")

    def test_ready_check_reports_external_profile_conflict_as_not_ready(self) -> None:
        resolved_account_id = uuid4()
        resolved_account = SimpleNamespace(id=resolved_account_id, display_name="Locked profile account")
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=resolved_account_id,
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        account_service = Mock()
        account_service.get_account.side_effect = lambda account_id: resolved_account if account_id == resolved_account_id else None
        account_service.health_summary.return_value = SimpleNamespace(health_status="HEALTHY", can_use_for_live_fetch=True)
        account_service.preflight_fetch_readiness.return_value = preflight_result(
            result="failed",
            category="fetch_not_ready",
            path=None,
            reopen_attempted=True,
            reopen_result="profile_locked_by_existing_process:Error",
            failure_code="profile_opened_outside_managed_runtime",
            failure_message="The saved Douyin browser profile is open outside the app-managed runtime.",
            watchdog_result="unavailable",
            watchdog_status="invalid",
            managed_runtime_status="profile_opened_outside_managed_runtime",
            profile_conflict_status="profile_opened_outside_managed_runtime",
        )

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
                summary = service.ready_check(workspace_id=None, requested_account_id=None, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "NOT_READY")
        self.assertFalse(summary.safe_to_run_intake_now)
        self.assertIsNone(summary.intended_fetch_path)
        self.assertEqual(summary.recommended_action, "go_to_accounts")
        self.assertEqual(summary.recommended_action_label, "Go to accounts")
        self.assertIn("open outside the app-managed runtime", summary.summary_message)

    def test_ready_check_reports_fallback_ready_when_legacy_http_fallback_enabled(self) -> None:
        resolved_account_id = uuid4()
        selected_account_id = uuid4()
        resolved_account = SimpleNamespace(id=resolved_account_id, display_name="Fallback account")
        selected_account = SimpleNamespace(id=selected_account_id, display_name="Selected account")
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=selected_account_id,
                resolved_account_id=resolved_account_id,
                selection_mode="fallback",
                selection_reason="selected_account_unusable",
                fallback_notice="Used fallback account",
            )
        )

        account_service = Mock()
        account_service.get_account.side_effect = lambda account_id: (
            selected_account if account_id == selected_account_id else resolved_account if account_id == resolved_account_id else None
        )
        account_service.health_summary.return_value = SimpleNamespace(health_status="STALE", can_use_for_live_fetch=True)
        account_service.preflight_fetch_readiness.return_value = preflight_result(
            category="fetch_ready_http_fallback",
            path="http_html",
            watchdog_result="missing",
            watchdog_status="none",
        )

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=True)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
                summary = service.ready_check(workspace_id=None, requested_account_id=selected_account_id, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "FALLBACK_READY")
        self.assertTrue(summary.safe_to_run_intake_now)
        self.assertEqual(summary.selected_account_label, "Selected account")
        self.assertEqual(summary.resolved_account_label, "Fallback account")
        self.assertEqual(summary.intended_fetch_path, "http_html")
        self.assertTrue(summary.fallback_allowed)
        self.assertEqual(summary.recommended_action, "run_intake_now")

    def test_ready_check_blocks_unresolved_browser_challenge(self) -> None:
        resolved_account_id = uuid4()
        resolved_account = SimpleNamespace(id=resolved_account_id, display_name="Challenge account")
        cooldown_until = datetime(2026, 4, 24, 20, 0, tzinfo=UTC)
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=resolved_account_id,
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        account_service = Mock()
        account_service.get_account.side_effect = lambda account_id: resolved_account if account_id == resolved_account_id else None
        account_service.health_summary.return_value = SimpleNamespace(health_status="BLOCKED", can_use_for_live_fetch=False)
        account_service.preflight_fetch_readiness.return_value = preflight_result(
            result="failed",
            category="fetch_blocked_by_browser_challenge",
            path=None,
            failure_code="challenge_cooldown_active",
            failure_message="Douyin challenge cooldown is active.",
            watchdog_result=None,
            watchdog_status=None,
            challenge_state="challenge_cooldown_active",
            challenge_category="challenge_required",
            challenge_count=2,
            challenge_cooldown_until=cooldown_until,
            challenge_recommended_next_action="wait_or_mark_challenge_solved_after_manual_completion",
        )

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
                summary = service.ready_check(workspace_id=None, requested_account_id=None, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "CHALLENGE_BLOCKED")
        self.assertFalse(summary.safe_to_run_intake_now)
        self.assertEqual(summary.recommended_action, "mark_challenge_solved")
        self.assertEqual(summary.fetch_readiness_category, "fetch_blocked_by_browser_challenge")
        self.assertEqual(summary.preflight_failure_code, "challenge_cooldown_active")
        self.assertEqual(summary.challenge_state, "challenge_cooldown_active")
        self.assertEqual(summary.challenge_category, "challenge_required")
        self.assertEqual(summary.challenge_count, 2)
        self.assertEqual(summary.challenge_cooldown_until, cooldown_until)
        self.assertEqual(summary.challenge_recommended_next_action, "wait_or_mark_challenge_solved_after_manual_completion")
        self.assertIn("Challenge cooldown active", summary.summary_message)

    def test_ready_check_reports_profile_quarantined_with_clean_profile_action(self) -> None:
        resolved_account_id = uuid4()
        resolved_account = SimpleNamespace(id=resolved_account_id, display_name="Quarantined account")
        recommendation = "Create and validate a fresh managed browser-backed profile."
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=resolved_account_id,
                resolved_account_id=resolved_account_id,
                selection_mode="selected",
                selection_reason="selected_account_requested",
                fallback_notice=None,
            )
        )

        account_service = Mock()
        account_service.get_account.side_effect = lambda account_id: resolved_account if account_id == resolved_account_id else None
        account_service.health_summary.return_value = SimpleNamespace(health_status="BLOCKED", can_use_for_live_fetch=False)
        account_service.preflight_fetch_readiness.return_value = preflight_result(
            result="failed",
            category="fetch_blocked_by_profile_quarantine",
            path=None,
            failure_code="profile_quarantined",
            failure_message="Profile quarantined. Create a fresh clean profile.",
            watchdog_result=None,
            watchdog_status=None,
            profile_quarantine_state="quarantined",
            profile_quarantine_reason="challenge_count_threshold_reached",
            profile_quarantine_detected=True,
            profile_quarantine_recommended_next_action="create_clean_managed_browser_profile",
            profile_quarantine_blocks_primary_flow=True,
            profile_quarantine_clean_profile_recommendation=recommendation,
        )

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
                summary = service.ready_check(workspace_id=None, requested_account_id=resolved_account_id, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "PROFILE_QUARANTINED")
        self.assertFalse(summary.safe_to_run_intake_now)
        self.assertEqual(summary.recommended_action, "create_clean_managed_browser_profile")
        self.assertEqual(summary.fetch_readiness_category, "fetch_blocked_by_profile_quarantine")
        self.assertEqual(summary.preflight_failure_code, "profile_quarantined")
        self.assertEqual(summary.profile_quarantine_state, "quarantined")
        self.assertEqual(summary.profile_quarantine_reason, "challenge_count_threshold_reached")
        self.assertTrue(summary.profile_quarantine_detected)
        self.assertTrue(summary.profile_quarantine_blocks_primary_flow)
        self.assertEqual(summary.profile_quarantine_recommended_next_action, "create_clean_managed_browser_profile")
        self.assertEqual(summary.profile_quarantine_clean_profile_recommendation, recommendation)
        self.assertIn("Profile quarantined", summary.summary_message)

    def test_ready_check_reports_pending_challenge_recheck_action(self) -> None:
        preflight = preflight_result(
            result="failed",
            category="fetch_blocked_by_browser_challenge",
            path=None,
            failure_code="challenge_recently_solved_pending_recheck",
            challenge_state="challenge_recently_solved_pending_recheck",
            challenge_category="manual_verification_required",
            challenge_count=1,
            challenge_recommended_next_action="retry_browser_validation_after_manual_solve",
        )
        service = IntakeDiscoveryService(Mock())

        status = service._ready_check_status(preflight=preflight)
        action, label = service._ready_check_recommended_action(readiness_status=status, preflight=preflight)
        message = service._ready_check_summary_message(readiness_status=status, account_label="Challenge account", preflight=preflight)

        self.assertEqual(status, "CHALLENGE_BLOCKED")
        self.assertEqual(action, "recheck_challenge")
        self.assertEqual(label, "Run post-challenge validation")
        self.assertIn("pending recheck", message)

    def test_ready_check_reports_not_ready_when_selection_fails(self) -> None:
        service = IntakeDiscoveryService(Mock())
        service._resolve_live_fetch_account_selection = Mock(
            side_effect=IntakeDiscoveryError(
                "account_resolution_failed",
                "No usable Douyin account is available for live fetch.",
                stage="resolve_account",
            )
        )

        with patch("src.services.intake_discovery_service.get_settings", return_value=SimpleNamespace(douyin_enable_legacy_http_fallback=False)):
            with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=Mock()):
                summary = service.ready_check(workspace_id=None, requested_account_id=None, profile_url=PROFILE_URL)

        self.assertEqual(summary.readiness_status, "NOT_READY")
        self.assertFalse(summary.safe_to_run_intake_now)
        self.assertEqual(summary.recommended_action, "go_to_accounts")
        self.assertEqual(summary.preflight_failure_code, "account_resolution_failed")

    def test_reuses_existing_profile_only_when_usable(self) -> None:
        profile = SimpleNamespace(id=uuid4(), source_profile_external_id="MS4wLjABAAAAfixture-sec-uid")
        service = IntakeDiscoveryService(Mock())
        service._find_existing_profile = Mock(return_value=profile)
        service._existing_profile_usability = Mock(
            return_value=ExistingProfileUsability(
                usable=True,
                video_count=2,
                latest_crawl_session_id=uuid4(),
                latest_crawl_status=CrawlSessionStatus.COMPLETED,
            )
        )

        with patch("src.services.intake_discovery_service.SourceIngestService") as ingest_cls, patch(
            "src.services.intake_discovery_service.CandidateEvaluationService"
        ) as candidate_cls:
            candidate_cls.return_value.apply.return_value = candidate_result()
            summary = service.discover(
                profile_url=PROFILE_URL,
                workspace_id=None,
                source_platform=SourcePlatformEnum.DOUYIN,
                preset_name=None,
                filter_config=None,
                persist=True,
            )

        ingest_cls.assert_not_called()
        self.assertTrue(summary.used_existing_profile)
        self.assertEqual(summary.fetch_mode, "existing_data")
        self.assertEqual(summary.videos_discovered_count, 2)

    def test_unusable_existing_profile_runs_live_ingest(self) -> None:
        old_profile = SimpleNamespace(id=uuid4(), source_profile_external_id="MS4wLjABAAAAfixture-sec-uid")
        refreshed_profile = SimpleNamespace(id=old_profile.id, source_profile_external_id="MS4wLjABAAAAfixture-sec-uid")
        db = Mock()
        db.get.return_value = refreshed_profile
        service = IntakeDiscoveryService(db)
        service._find_existing_profile = Mock(return_value=old_profile)
        service._existing_profile_usability = Mock(
            return_value=ExistingProfileUsability(
                usable=False,
                video_count=0,
                latest_crawl_session_id=None,
                latest_crawl_status=None,
                reason="no source videos",
            )
        )
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=uuid4(),
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        with patch("src.services.intake_discovery_service.DouyinAccountService") as account_cls, patch(
            "src.services.intake_discovery_service.SourceIngestService"
        ) as ingest_cls, patch(
            "src.services.intake_discovery_service.CandidateEvaluationService"
        ) as candidate_cls:
            account_cls.return_value.preflight_fetch_readiness.return_value = preflight_result()
            account_cls.return_value.build_douyin_adapter.return_value = object()
            ingest_cls.return_value.ingest_profile.return_value = ingest_summary(refreshed_profile.id)
            candidate_cls.return_value.apply.return_value = candidate_result()
            summary = service.discover(
                profile_url=PROFILE_URL,
                workspace_id=None,
                source_platform=SourcePlatformEnum.DOUYIN,
                preset_name=None,
                filter_config=None,
                persist=True,
            )

        ingest_cls.assert_called_once()
        constructor_args, constructor_kwargs = ingest_cls.call_args
        self.assertEqual(constructor_args[0], db)
        self.assertIn(SourcePlatformEnum.DOUYIN, constructor_kwargs["adapters"])
        ingest_cls.return_value.ingest_profile.assert_called_once()
        self.assertFalse(summary.used_existing_profile)
        self.assertEqual(summary.fetch_mode, "live_fetch_using_account")
        self.assertEqual(summary.videos_discovered_count, 3)
        self.assertIn("not reusable", summary.warning or "")

    def test_force_live_refresh_skips_usable_existing_profile(self) -> None:
        profile = SimpleNamespace(id=uuid4(), source_profile_external_id="MS4wLjABAAAAfixture-sec-uid")
        db = Mock()
        db.get.return_value = profile
        service = IntakeDiscoveryService(db)
        service._find_existing_profile = Mock(return_value=profile)
        service._existing_profile_usability = Mock()
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=uuid4(),
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        with patch("src.services.intake_discovery_service.DouyinAccountService") as account_cls, patch(
            "src.services.intake_discovery_service.SourceIngestService"
        ) as ingest_cls, patch(
            "src.services.intake_discovery_service.CandidateEvaluationService"
        ) as candidate_cls:
            account_cls.return_value.preflight_fetch_readiness.return_value = preflight_result()
            account_cls.return_value.build_douyin_adapter.return_value = object()
            ingest_cls.return_value.ingest_profile.return_value = ingest_summary(profile.id)
            candidate_cls.return_value.apply.return_value = candidate_result()
            summary = service.discover(
                profile_url=PROFILE_URL,
                workspace_id=None,
                source_platform=SourcePlatformEnum.DOUYIN,
                preset_name=None,
                filter_config=None,
                persist=True,
                force_live_refresh=True,
            )

        service._existing_profile_usability.assert_not_called()
        ingest_cls.return_value.ingest_profile.assert_called_once()
        self.assertFalse(summary.used_existing_profile)
        self.assertEqual(summary.fetch_mode, "forced_live_fetch_using_account")
        self.assertIn("Force live refresh", summary.warning or "")


    def test_selected_unusable_account_falls_back_to_best_usable(self) -> None:
        selected = SimpleNamespace(
            id=uuid4(),
            display_name="Selected",
            last_successful_validation_at=None,
            updated_at=None,
            is_default=False,
        )
        healthy = SimpleNamespace(
            id=uuid4(),
            display_name="Healthy A",
            last_successful_validation_at=None,
            updated_at=None,
            is_default=True,
        )
        service = IntakeDiscoveryService(Mock())

        account_service = Mock()
        account_service.list_accounts.return_value = [selected, healthy]
        account_service.default_account.return_value = healthy

        def health_summary(account):
            if account.id == selected.id:
                return SimpleNamespace(health_status="INVALID", can_use_for_live_fetch=False)
            return SimpleNamespace(health_status="HEALTHY", can_use_for_live_fetch=True)

        account_service.health_summary.side_effect = health_summary

        with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
            selection = service._resolve_live_fetch_account_selection(
                workspace_id=None,
                requested_account_id=selected.id,
            )

        self.assertEqual(selection.selection_mode, "fallback")
        self.assertEqual(selection.selection_reason, "selected_account_unusable")
        self.assertEqual(selection.selected_account_id, selected.id)
        self.assertEqual(selection.resolved_account_id, healthy.id)
        self.assertIsNotNone(selection.fallback_notice)

    def test_no_usable_accounts_raises_required_error(self) -> None:
        account = SimpleNamespace(
            id=uuid4(),
            display_name="Only",
            last_successful_validation_at=None,
            updated_at=None,
            is_default=True,
        )
        service = IntakeDiscoveryService(Mock())

        account_service = Mock()
        account_service.list_accounts.return_value = [account]
        account_service.default_account.return_value = account
        account_service.health_summary.return_value = SimpleNamespace(health_status="INVALID", can_use_for_live_fetch=False)

        with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
            with self.assertRaisesRegex(Exception, "No usable Douyin account"):
                service._resolve_live_fetch_account_selection(
                    workspace_id=None,
                    requested_account_id=None,
                )

    def test_selected_imported_account_surfaces_specific_missing_user_agent_error(self) -> None:
        selected = SimpleNamespace(
            id=uuid4(),
            display_name="Imported account",
            last_successful_validation_at=None,
            updated_at=None,
            is_default=False,
            last_error_code="imported_session_missing_user_agent",
        )
        service = IntakeDiscoveryService(Mock())

        account_service = Mock()
        account_service.list_accounts.return_value = [selected]
        account_service.default_account.return_value = None
        account_service.health_summary.return_value = SimpleNamespace(health_status="INVALID", can_use_for_live_fetch=False)

        with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
            with self.assertRaises(IntakeDiscoveryError) as ctx:
                service._resolve_live_fetch_account_selection(
                    workspace_id=None,
                    requested_account_id=selected.id,
                )

        self.assertEqual(ctx.exception.code, "missing_user_agent")
        self.assertEqual(ctx.exception.stage, "resolve_account")

    def test_selected_imported_account_surfaces_cookie_too_thin_error(self) -> None:
        selected = SimpleNamespace(
            id=uuid4(),
            display_name="Imported account",
            last_successful_validation_at=None,
            updated_at=None,
            is_default=False,
            last_error_code="imported_session_cookie_too_thin",
        )
        service = IntakeDiscoveryService(Mock())

        account_service = Mock()
        account_service.list_accounts.return_value = [selected]
        account_service.default_account.return_value = None
        account_service.health_summary.return_value = SimpleNamespace(health_status="INVALID", can_use_for_live_fetch=False)

        with patch("src.services.intake_discovery_service.DouyinAccountService", return_value=account_service):
            with self.assertRaises(IntakeDiscoveryError) as ctx:
                service._resolve_live_fetch_account_selection(
                    workspace_id=None,
                    requested_account_id=selected.id,
                )

        self.assertEqual(ctx.exception.code, "imported_session_cookie_too_thin")
        self.assertEqual(ctx.exception.stage, "resolve_account")

    def test_ingest_source_error_is_mapped_with_stage_and_diagnostics(self) -> None:
        profile = SimpleNamespace(id=uuid4(), source_profile_external_id="MS4wLjABAAAAfixture-sec-uid")
        db = Mock()
        service = IntakeDiscoveryService(db)
        service._find_existing_profile = Mock(return_value=None)
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=uuid4(),
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        with patch("src.services.intake_discovery_service.DouyinAccountService") as account_cls, patch(
            "src.services.intake_discovery_service.SourceIngestService"
        ) as ingest_cls:
            account_cls.return_value.preflight_fetch_readiness.return_value = preflight_result()
            account_cls.return_value.build_douyin_adapter.return_value = object()
            ingest_cls.return_value.ingest_profile.side_effect = SourceIngestError(
                SourceAdapterErrorCode.NORMALIZATION_FAILED,
                "Douyin videos payload must be a list",
            )

            with self.assertRaises(IntakeDiscoveryError) as ctx:
                service.discover(
                    profile_url=PROFILE_URL,
                    workspace_id=None,
                    source_platform=SourcePlatformEnum.DOUYIN,
                    preset_name=None,
                    filter_config=None,
                    persist=True,
                )

        self.assertEqual(ctx.exception.code, "normalize_failed")
        self.assertEqual(ctx.exception.stage, "normalize_payload")
        self.assertTrue(ctx.exception.diagnostics_id)

    def test_preflight_failure_stops_before_live_ingest(self) -> None:
        profile = SimpleNamespace(id=uuid4(), source_profile_external_id="MS4wLjABAAAAfixture-sec-uid")
        db = Mock()
        service = IntakeDiscoveryService(db)
        service._find_existing_profile = Mock(return_value=None)
        service._resolve_live_fetch_account_selection = Mock(
            return_value=SimpleNamespace(
                selected_account_id=None,
                resolved_account_id=uuid4(),
                selection_mode="default",
                selection_reason="default_account_usable",
                fallback_notice=None,
            )
        )

        with patch("src.services.intake_discovery_service.DouyinAccountService") as account_cls, patch(
            "src.services.intake_discovery_service.SourceIngestService"
        ) as ingest_cls:
            account_cls.return_value.preflight_fetch_readiness.return_value = preflight_result(
                result="failed",
                category="fetch_not_ready",
                path=None,
                failure_code="account_not_fetch_ready",
                failure_message="Selected account is not fetch-ready.",
            )

            with self.assertRaises(IntakeDiscoveryError) as ctx:
                service.discover(
                    profile_url=PROFILE_URL,
                    workspace_id=None,
                    source_platform=SourcePlatformEnum.DOUYIN,
                    preset_name=None,
                    filter_config=None,
                    persist=True,
                )

        ingest_cls.assert_not_called()
        self.assertEqual(ctx.exception.stage, "preflight_fetch")
        self.assertEqual(ctx.exception.code, "account_not_fetch_ready")
        self.assertEqual(ctx.exception.details["preflight"]["preflight_result"], "failed")

    def test_ingest_parse_zero_videos_error_is_mapped_explicitly(self) -> None:
        service = IntakeDiscoveryService(Mock())
        exc = SourceIngestError(
            SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
            "Douyin returned an HTML shell without parseable embedded profile videos.",
            raw_payload={
                "metadata": {
                    "response_classification": {
                        "code": "parse_zero_videos",
                        "message": "Douyin returned an HTML shell without parseable embedded profile videos.",
                    }
                }
            },
        )

        code, message, stage = service._classify_ingest_error(exc)

        self.assertEqual(code, "parse_zero_videos")
        self.assertEqual(stage, "classify_response")
        self.assertIn("HTML shell", message)

    def test_completed_zero_video_run_is_classified_as_fetch_issue(self) -> None:
        service = IntakeDiscoveryService(Mock())
        crawl = SimpleNamespace(
            status=CrawlSessionStatus.COMPLETED,
            metadata_json={
                "fetch_observability": {
                    "stages": {
                        "response_classification": {
                            "code": "parse_zero_videos",
                            "message": "Douyin returned an HTML shell without parseable embedded profile videos.",
                        }
                    }
                }
            },
            raw_summary_json={
                "parse_strategy": "videos",
                "normalized_video_count": 0,
                "response_classification_code": "parse_zero_videos",
                "response_classification_message": "Douyin returned an HTML shell without parseable embedded profile videos.",
            },
            result_summary_json={"persisted_video_count": 0},
            videos_created_count=0,
            videos_updated_count=0,
        )

        summary = service._fetch_stage_summary_from_crawl(crawl, videos_discovered_count=0)

        self.assertEqual(summary.code, "parse_zero_videos")
        self.assertEqual(summary.stage, "classify_response")
        self.assertIn("HTML shell", summary.message)


if __name__ == "__main__":
    unittest.main()
