from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.enums import CapturedItemStatus
from src.services.capture_inbox_metadata_hydration_service import (
    CaptureInboxMetadataHydrationService,
    CaptureInboxMetadataHydrationError,
    _sanitize_detail_aweme,
    classify_detail_page_access,
    extract_detail_aweme_from_browser_artifacts,
)


class CaptureInboxMetadataHydrationServiceTests(unittest.TestCase):
    def test_detail_parser_extracts_nested_aweme_by_exact_id(self) -> None:
        html = """
        <html><body><script>
        window.__INITIAL_STATE__ = {"foo":{"aweme":{"aweme_id":"7420000000000000001","create_time":1710000000,"video":{"duration":42000},"statistics":{"play_count":100,"digg_count":5}}}};
        </script></body></html>
        """

        result = extract_detail_aweme_from_browser_artifacts(
            target_aweme_id="7420000000000000001",
            html=html,
            response_documents=None,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["aweme_id"], "7420000000000000001")
        self.assertEqual(result["video"]["duration"], 42000)
        self.assertEqual(result["statistics"]["play_count"], 100)

    def test_detail_parser_rejects_mismatched_aweme_id(self) -> None:
        html = """
        <html><body><script>
        window.__INITIAL_STATE__ = {"foo":{"aweme":{"aweme_id":"7420000000000000001","video":{"duration":42000}}}};
        </script></body></html>
        """

        result = extract_detail_aweme_from_browser_artifacts(
            target_aweme_id="7420000000000000999",
            html=html,
            response_documents=None,
        )

        self.assertIsNone(result)

    def test_captcha_html_is_detected(self) -> None:
        issue = classify_detail_page_access(
            page_url="https://www.douyin.com/verify",
            title="请完成验证",
            html="<html><body>验证码中间页 请完成验证</body></html>",
            response_documents=None,
        )

        self.assertEqual(issue, ("captcha_required", "detail_page_captcha"))

    def test_normal_detail_html_is_not_falsely_classified_as_captcha(self) -> None:
        issue = classify_detail_page_access(
            page_url="https://www.douyin.com/video/7420000000000000001",
            title="Douyin video",
            html="<html><body><script>window.__INITIAL_STATE__={\"aweme\":{\"aweme_id\":\"7420000000000000001\"}}</script></body></html>",
            response_documents=[{"aweme_detail": {"aweme_id": "7420000000000000001"}}],
        )

        self.assertIsNone(issue)

    def test_sanitizer_removes_secret_like_keys_and_caps_large_data(self) -> None:
        raw = {
            "aweme_id": 7420000000000000001,
            "video": {
                "duration": 42000,
                "authorization_header": "secret",
                "nested": {"cookie_token": "secret", "value": "x" * 800},
            },
            "statistics": {"play_count": 100},
            "author": {"name": "creator", "msToken": "drop-me"},
            "desc": "y" * 900,
        }

        result = _sanitize_detail_aweme(raw)

        self.assertEqual(result["aweme_id"], "7420000000000000001")
        self.assertNotIn("authorization_header", result["video"])
        self.assertNotIn("cookie_token", result["video"]["nested"])
        self.assertNotIn("msToken", result["author"])
        self.assertLessEqual(len(result["desc"]), 500)

    def test_hydrate_item_updates_raw_detail_and_reuses_normalizer(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxMetadataHydrationService(db)
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            source_url="https://www.douyin.com/video/7420000000000000001",
            share_url=None,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
            metadata_json={"raw_dom_snapshot": {"visible_text": "Fixture DOM"}},
            posted_at=None,
            duration_seconds=None,
        )
        fetch_result = SimpleNamespace(
            available=True,
            html="<html></html>",
            response_documents=[
                {
                    "aweme_detail": {
                        "aweme_id": "7420000000000000001",
                        "create_time": 1710000000,
                        "video": {"duration": 42000},
                        "statistics": {"play_count": 100, "digg_count": 5, "comment_count": 2, "share_count": 1},
                    }
                }
            ],
        )

        with patch(
            "src.services.capture_inbox_metadata_hydration_service.douyin_browser_context_registry.fetch_detail_page",
            return_value=fetch_result,
        ):
            result = service._hydrate_item(item, account_id=uuid4(), timeout_seconds=8.0)

        self.assertEqual(result.outcome, "hydrated")
        self.assertEqual(item.duration_seconds, 42.0)
        self.assertIsNotNone(item.posted_at)
        self.assertEqual(item.metadata_json["view_count"], 100)
        self.assertEqual(item.metadata_json["like_count"], 5)
        self.assertTrue(item.metadata_json["raw_evidence_summary"]["has_detail_aweme"])
        self.assertEqual(item.metadata_json["duration_source"], "detail_hydrate")
        self.assertEqual(item.metadata_json["view_count_source"], "detail_hydrate")

    def test_hydrate_item_does_not_parse_captcha_as_raw_detail_aweme(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxMetadataHydrationService(db)
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            source_url="https://www.douyin.com/video/7420000000000000001",
            share_url=None,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
            metadata_json={},
            posted_at=None,
            duration_seconds=None,
        )
        fetch_result = SimpleNamespace(
            available=True,
            page_url="https://www.douyin.com/verify",
            title="请完成验证",
            html="<html><body>验证码中间页</body></html>",
            response_documents=[],
        )

        with patch(
            "src.services.capture_inbox_metadata_hydration_service.douyin_browser_context_registry.fetch_detail_page",
            return_value=fetch_result,
        ):
            result = service._hydrate_item(item, account_id=uuid4(), timeout_seconds=8.0)

        self.assertEqual(result.outcome, "captcha_required")
        self.assertNotIn("raw_detail_aweme", item.metadata_json)
        self.assertEqual(item.metadata_json["metadata_hydration_error_code"], "captcha_required")
        self.assertEqual(item.metadata_json["performance_missing_reason"], "captcha_required")
        self.assertEqual(item.metadata_json["processing_fit_missing_reason"], "captcha_required")

    def test_item_level_failure_does_not_fail_whole_session(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxMetadataHydrationService(db)
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            items=[
                SimpleNamespace(id=uuid4(), status=CapturedItemStatus.NEEDS_ENRICHMENT, metadata_json={}, duration_seconds=None),
                SimpleNamespace(id=uuid4(), status=CapturedItemStatus.NEEDS_ENRICHMENT, metadata_json={}, duration_seconds=None),
            ],
            metadata_json={},
        )
        account = SimpleNamespace(id=uuid4())
        preflight = SimpleNamespace(preflight_result="passed", selected_fetch_path="browser_profile")
        hydrate_results = [
            SimpleNamespace(
                item_id=session.items[0].id,
                aweme_id="1",
                detail_url="https://www.douyin.com/video/1",
                outcome="hydrated",
                message="ok",
                duration_seconds=10.0,
                view_count=1,
                like_count=1,
                comment_count=0,
                share_count=0,
            ),
            SimpleNamespace(
                item_id=session.items[1].id,
                aweme_id="2",
                detail_url="https://www.douyin.com/video/2",
                outcome="failed",
                message="detail_aweme_not_found",
                duration_seconds=None,
                view_count=None,
                like_count=None,
                comment_count=None,
                share_count=None,
            ),
        ]

        with patch.object(service, "_get_capture_session", return_value=session), patch.object(
            service,
            "_resolve_browser_backed_account",
            return_value=(account, preflight),
        ), patch.object(service, "_needs_hydration", return_value=True), patch.object(
            service,
            "_ensure_browser_context_for_hydration",
        ), patch.object(
            service,
            "_hydrate_item",
            side_effect=hydrate_results,
        ):
            result = service.hydrate_capture_session_metadata(session.id)

        self.assertEqual(result.hydrated_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.detail_hydrate_attempted_count, 2)

    def test_hydration_ensures_browser_context_before_item_loop(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxMetadataHydrationService(db)
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            items=[SimpleNamespace(id=uuid4(), status=CapturedItemStatus.NEEDS_ENRICHMENT, metadata_json={}, duration_seconds=None)],
            metadata_json={},
        )
        account = SimpleNamespace(id=uuid4())
        preflight = SimpleNamespace(preflight_result="passed", selected_fetch_path="browser_profile")
        hydrated = SimpleNamespace(
            item_id=session.items[0].id,
            aweme_id="1",
            detail_url="https://www.douyin.com/video/1",
            outcome="hydrated",
            message="ok",
            duration_seconds=1.0,
            view_count=1,
            like_count=1,
            comment_count=0,
            share_count=0,
        )

        with patch.object(service, "_get_capture_session", return_value=session), patch.object(
            service,
            "_resolve_browser_backed_account",
            return_value=(account, preflight),
        ), patch.object(service, "_needs_hydration", return_value=True), patch.object(
            service,
            "_ensure_browser_context_for_hydration",
        ) as ensure_context, patch.object(service, "_hydrate_item", return_value=hydrated) as hydrate_item:
            result = service.hydrate_capture_session_metadata(session.id)

        ensure_context.assert_called_once_with(account=account, total_items_considered=1)
        hydrate_item.assert_called_once()
        self.assertEqual(result.detail_hydrate_attempted_count, 1)

    def test_context_open_failure_stops_session_before_item_loop(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxMetadataHydrationService(db)
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            items=[SimpleNamespace(id=uuid4(), status=CapturedItemStatus.NEEDS_ENRICHMENT, metadata_json={}, duration_seconds=None)],
            metadata_json={},
        )
        account = SimpleNamespace(id=uuid4())
        preflight = SimpleNamespace(preflight_result="passed", selected_fetch_path="browser_profile")

        with patch.object(service, "_get_capture_session", return_value=session), patch.object(
            service,
            "_resolve_browser_backed_account",
            return_value=(account, preflight),
        ), patch.object(service, "_needs_hydration", return_value=True), patch.object(
            service,
            "_ensure_browser_context_for_hydration",
            side_effect=CaptureInboxMetadataHydrationError(
                "browser_context_unavailable",
                "Saved browser profile could not provide a live browser context for hydration.",
                details={
                    "account_id": str(account.id),
                    "selected_fetch_path": "browser_profile",
                    "total_items_considered": 1,
                    "detail_hydrate_attempted_count": 0,
                },
            ),
        ), patch.object(service, "_hydrate_item") as hydrate_item:
            with self.assertRaises(CaptureInboxMetadataHydrationError) as captured:
                service.hydrate_capture_session_metadata(session.id)

        hydrate_item.assert_not_called()
        self.assertEqual(captured.exception.code, "browser_context_unavailable")
        self.assertEqual(captured.exception.details["detail_hydrate_attempted_count"], 0)

    def test_session_hydration_stops_when_captcha_is_detected(self) -> None:
        db = SimpleNamespace(add=lambda item: None, commit=lambda: None)
        service = CaptureInboxMetadataHydrationService(db)
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            items=[
                SimpleNamespace(id=uuid4(), status=CapturedItemStatus.NEEDS_ENRICHMENT, metadata_json={}, duration_seconds=None),
                SimpleNamespace(id=uuid4(), status=CapturedItemStatus.NEEDS_ENRICHMENT, metadata_json={}, duration_seconds=None),
            ],
            metadata_json={},
        )
        account = SimpleNamespace(id=uuid4())
        preflight = SimpleNamespace(preflight_result="passed", selected_fetch_path="browser_profile")
        hydrate_results = [
            SimpleNamespace(
                item_id=session.items[0].id,
                aweme_id="1",
                detail_url="https://www.douyin.com/video/1",
                outcome="captcha_required",
                message="detail_page_captcha",
                duration_seconds=None,
                view_count=None,
                like_count=None,
                comment_count=None,
                share_count=None,
            ),
            SimpleNamespace(
                item_id=session.items[1].id,
                aweme_id="2",
                detail_url="https://www.douyin.com/video/2",
                outcome="hydrated",
                message="should_not_run",
                duration_seconds=10.0,
                view_count=1,
                like_count=1,
                comment_count=0,
                share_count=0,
            ),
        ]

        with patch.object(service, "_get_capture_session", return_value=session), patch.object(
            service,
            "_resolve_browser_backed_account",
            return_value=(account, preflight),
        ), patch.object(service, "_needs_hydration", return_value=True), patch.object(
            service,
            "_ensure_browser_context_for_hydration",
        ), patch.object(
            service,
            "_hydrate_item",
            side_effect=hydrate_results,
        ):
            with self.assertRaises(CaptureInboxMetadataHydrationError) as captured:
                service.hydrate_capture_session_metadata(session.id)

        self.assertEqual(captured.exception.code, "captcha_required")
        self.assertEqual(captured.exception.details["captcha_required_count"], 1)
        self.assertEqual(captured.exception.details["hydrated_count"], 0)
        self.assertEqual(session.metadata_json["last_metadata_hydration_run"]["stop_reason_code"], "captcha_required")

    def test_resolve_browser_backed_account_accepts_operator_confirmed_preflight(self) -> None:
        db = SimpleNamespace()
        service = CaptureInboxMetadataHydrationService(db)
        workspace_id = uuid4()
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            workspace_id=workspace_id,
            metadata_json={"browser_profile_id": "profile-1", "browser_profile_path": "C:/profiles/profile-1"},
        )
        preflight = SimpleNamespace(
            preflight_result="passed",
            selected_fetch_path="browser_profile",
            fetch_readiness_category="fetch_ready_operator_confirmed",
        )

        with patch("src.services.capture_inbox_metadata_hydration_service.DouyinAccountService") as service_cls:
            service_cls.return_value.get_account.return_value = account
            service_cls.return_value.preflight_fetch_readiness.return_value = preflight

            resolved_account, resolved_preflight = service._resolve_browser_backed_account(
                workspace_id=workspace_id,
                requested_account_id=account_id,
            )

        self.assertIs(resolved_account, account)
        self.assertIs(resolved_preflight, preflight)

    def test_ensure_browser_context_for_hydration_recovers_missing_live_context_by_reopening_profile(self) -> None:
        db = Mock()
        service = CaptureInboxMetadataHydrationService(db)
        account = SimpleNamespace(id=uuid4())

        with patch("src.services.capture_inbox_metadata_hydration_service.DouyinAccountService") as account_service_cls, patch(
            "src.services.capture_inbox_metadata_hydration_service.douyin_browser_context_registry"
        ) as registry:
            account_service_cls.return_value._ensure_persistent_profile_context.return_value = SimpleNamespace(
                status="active",
                reason="reopen_success",
                runtime_context_id="runtime-1",
            )
            registry.summary_for_account.side_effect = [
                SimpleNamespace(status="none", reason="no_live_browser_context"),
                SimpleNamespace(status="active", reason="reopen_success"),
            ]
            registry.validate_account_context.return_value = SimpleNamespace(
                status="uncertain",
                reason="browser_prevalidation_navigation_uncertain",
                runtime_attach_status="managed_runtime_active",
            )

            service._ensure_browser_context_for_hydration(account=account, total_items_considered=49)

        account_service_cls.return_value._ensure_persistent_profile_context.assert_called_once_with(
            account,
            purpose="fetch",
            force=True,
        )
        db.commit.assert_called_once()
        registry.validate_account_context.assert_called_once_with(account.id, validation_url="https://www.douyin.com/")

    def test_ensure_browser_context_for_hydration_raises_once_when_context_cannot_open(self) -> None:
        db = Mock()
        service = CaptureInboxMetadataHydrationService(db)
        account = SimpleNamespace(id=uuid4())

        with patch("src.services.capture_inbox_metadata_hydration_service.DouyinAccountService") as account_service_cls, patch(
            "src.services.capture_inbox_metadata_hydration_service.douyin_browser_context_registry"
        ) as registry:
            account_service_cls.return_value._ensure_persistent_profile_context.return_value = SimpleNamespace(
                status="invalid",
                reason="first_page_closed_early:TargetClosedError",
                runtime_context_id=None,
            )
            registry.summary_for_account.side_effect = [
                SimpleNamespace(status="none", reason="no_live_browser_context"),
                SimpleNamespace(status="none", reason="no_live_browser_context"),
            ]

            with self.assertRaises(CaptureInboxMetadataHydrationError) as captured:
                service._ensure_browser_context_for_hydration(account=account, total_items_considered=49)

        self.assertEqual(captured.exception.code, "profile_open_failed")
        self.assertEqual(captured.exception.details["detail_hydrate_attempted_count"], 0)

    def test_complete_items_are_skipped_unless_forced(self) -> None:
        service = CaptureInboxMetadataHydrationService(SimpleNamespace())
        item = SimpleNamespace(
            status=CapturedItemStatus.READY,
            duration_seconds=42.0,
            metadata_json={
                "performance_status": "captured",
                "processing_fit_status": "captured",
                "view_count": 10,
                "like_count": 2,
            },
        )

        self.assertFalse(service._needs_hydration(item, force=False))
        self.assertTrue(service._needs_hydration(item, force=True))

    def test_old_rows_without_source_url_fall_back_to_video_url(self) -> None:
        service = CaptureInboxMetadataHydrationService(SimpleNamespace())
        item = SimpleNamespace(
            source_url=None,
            source_video_external_id="7420000000000000001",
        )

        detail_url = service._detail_url_for_item(item, "7420000000000000001")

        self.assertEqual(detail_url, "https://www.douyin.com/video/7420000000000000001")


if __name__ == "__main__":
    unittest.main()
