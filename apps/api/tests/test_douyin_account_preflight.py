from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.services.douyin_account_service import DouyinAccountService


class DouyinAccountPreflightTests(unittest.TestCase):
    def test_passed_preflight_is_cached_briefly(self) -> None:
        account = SimpleNamespace(
            id=uuid4(),
            metadata_json={},
            user_agent="Mozilla/5.0 test",
            headers_json=None,
        )
        settings = SimpleNamespace(
            douyin_intake_preflight_cache_ttl_seconds=30,
            douyin_prefer_browser_profile_for_fetch=True,
            douyin_enable_legacy_http_fallback=True,
        )
        service = DouyinAccountService(Mock())
        service.invalidate_preflight_cache(account.id)
        service.get_account = Mock(return_value=account)
        service.health_summary = Mock(return_value=SimpleNamespace(can_use_for_live_fetch=True, health_status="healthy"))
        service._has_http_fetch_material = Mock(return_value=True)

        with patch("src.services.douyin_account_service.get_settings", return_value=settings):
            first = service.preflight_fetch_readiness(account.id)
            second = service.preflight_fetch_readiness(account.id)

        self.assertEqual(first.preflight_result, "passed")
        self.assertFalse(first.preflight_cached)
        self.assertEqual(second.preflight_result, "passed")
        self.assertTrue(second.preflight_cached)
        self.assertEqual(second.browser_reopen_result, "cache_hit")
        service._has_http_fetch_material.assert_called_once_with(account)

        service.invalidate_preflight_cache(account.id)

    def test_failed_health_preflight_is_not_cached(self) -> None:
        account = SimpleNamespace(id=uuid4(), metadata_json={})
        settings = SimpleNamespace(
            douyin_intake_preflight_cache_ttl_seconds=30,
            douyin_prefer_browser_profile_for_fetch=True,
            douyin_enable_legacy_http_fallback=False,
        )
        service = DouyinAccountService(Mock())
        service.invalidate_preflight_cache(account.id)
        service.get_account = Mock(return_value=account)
        service.health_summary = Mock(return_value=SimpleNamespace(can_use_for_live_fetch=False, health_status="blocked"))

        with patch("src.services.douyin_account_service.get_settings", return_value=settings):
            first = service.preflight_fetch_readiness(account.id)
            second = service.preflight_fetch_readiness(account.id)

        self.assertEqual(first.preflight_result, "failed")
        self.assertFalse(first.preflight_cached)
        self.assertEqual(second.preflight_result, "failed")
        self.assertFalse(second.preflight_cached)
        self.assertEqual(service.health_summary.call_count, 2)

    def test_quarantined_profile_blocks_preflight_and_recommends_clean_profile(self) -> None:
        account = SimpleNamespace(
            id=uuid4(),
            metadata_json={
                "browser_profile_id": "profile-1",
                "douyin_challenge_count": 3,
            },
            user_agent="Mozilla/5.0 test",
            headers_json=None,
        )
        settings = SimpleNamespace(
            douyin_intake_preflight_cache_ttl_seconds=30,
            douyin_prefer_browser_profile_for_fetch=True,
            douyin_enable_legacy_http_fallback=True,
        )
        service = DouyinAccountService(Mock())
        service.invalidate_preflight_cache(account.id)
        service.get_account = Mock(return_value=account)
        service._has_http_fetch_material = Mock(return_value=True)

        with patch("src.services.douyin_account_service.get_settings", return_value=settings):
            result = service.preflight_fetch_readiness(account.id)
        persisted_metadata = service.get_account.return_value.metadata_json

        self.assertEqual(result.preflight_result, "failed")
        self.assertEqual(result.fetch_readiness_category, "fetch_blocked_by_profile_quarantine")
        self.assertEqual(result.preflight_failure_code, "profile_quarantined")
        self.assertIsNone(result.selected_fetch_path)
        self.assertTrue(result.browser_profile_available)
        self.assertEqual(result.profile_quarantine_state, "quarantined")
        self.assertEqual(result.profile_quarantine_reason, "challenge_count_threshold_reached")
        self.assertTrue(result.profile_quarantine_detected)
        self.assertTrue(result.profile_quarantine_blocks_primary_flow)
        self.assertEqual(result.profile_quarantine_recommended_next_action, "create_clean_managed_browser_profile")
        self.assertIn("fresh managed browser-backed account/profile", result.profile_quarantine_clean_profile_recommendation or "")
        self.assertEqual(persisted_metadata["douyin_profile_quarantine_state"], "quarantined")
        self.assertEqual(persisted_metadata["douyin_profile_quarantine_reason"], "challenge_count_threshold_reached")
        service._has_http_fetch_material.assert_not_called()

    def test_browser_profile_is_required_when_legacy_http_fallback_is_disabled(self) -> None:
        account = SimpleNamespace(
            id=uuid4(),
            metadata_json={},
            user_agent="Mozilla/5.0 test",
            headers_json=None,
        )
        settings = SimpleNamespace(
            douyin_intake_preflight_cache_ttl_seconds=30,
            douyin_prefer_browser_profile_for_fetch=True,
            douyin_enable_legacy_http_fallback=False,
        )
        service = DouyinAccountService(Mock())
        service.invalidate_preflight_cache(account.id)
        service.get_account = Mock(return_value=account)
        service.health_summary = Mock(return_value=SimpleNamespace(can_use_for_live_fetch=True, health_status="healthy"))
        service._has_http_fetch_material = Mock(return_value=True)

        with patch("src.services.douyin_account_service.get_settings", return_value=settings):
            result = service.preflight_fetch_readiness(account.id)

        self.assertEqual(result.preflight_result, "failed")
        self.assertEqual(result.preflight_failure_code, "browser_profile_required")
        service._has_http_fetch_material.assert_not_called()


if __name__ == "__main__":
    unittest.main()
