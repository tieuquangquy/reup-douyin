from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.adapters.types import IngestSummary
from src.enums import CrawlSessionStatus, SourcePlatformEnum
from src.models.ingestion import SourceProfile
from src.services.douyin_current_page_capture_service import (
    DouyinCurrentPageCaptureError,
    DouyinCurrentPageCaptureService,
    classify_current_page,
    profile_url_from_current_page,
)


class DouyinCurrentPageCaptureServiceTests(unittest.TestCase):
    def test_classifies_required_page_taxonomy(self) -> None:
        self.assertEqual(classify_current_page(page_url=None, title=None, body_text=None), "unknown_page")
        self.assertEqual(classify_current_page(page_url="https://example.com", title="", body_text=""), "unsupported_page")
        self.assertEqual(classify_current_page(page_url="https://www.douyin.com/passport/login", title="Login", body_text=""), "login_page")
        self.assertEqual(classify_current_page(page_url="https://www.douyin.com/user/abc", title="", body_text="验证码"), "challenge_page")
        self.assertEqual(classify_current_page(page_url="https://www.douyin.com/", title="", body_text=""), "home_feed_page")
        self.assertEqual(classify_current_page(page_url="https://www.douyin.com/user/MS4w", title="", body_text="", video_link_count=0), "profile_page")
        self.assertEqual(classify_current_page(page_url="https://www.douyin.com/user/MS4w", title="", body_text="", video_link_count=3), "profile_feed_page")
        self.assertEqual(classify_current_page(page_url="https://www.douyin.com/video/7420000000000000001", title="", body_text=""), "video_detail_page")

    def test_profile_url_from_current_page_normalizes_supported_profile_forms(self) -> None:
        self.assertEqual(
            profile_url_from_current_page("https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid?from=feed"),
            "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
        )
        self.assertEqual(
            profile_url_from_current_page("https://www.douyin.com/@fixture_creator/video"),
            "https://www.douyin.com/@fixture_creator",
        )
        self.assertIsNone(profile_url_from_current_page("https://example.com/user/MS4w"))

    def test_detect_current_page_reports_unavailable_runtime_without_capture_support(self) -> None:
        account_id = uuid4()
        snapshot = SimpleNamespace(
            available=False,
            page_url=None,
            title=None,
            body_text=None,
            video_link_count=0,
            runtime_context_id=None,
            runtime_attach_status="runtime_missing_reopen_required",
            page_recovery_status=None,
            managed_runtime_status="managed_runtime_missing",
            reason="no_live_browser_context",
        )
        with patch("src.services.douyin_current_page_capture_service.douyin_browser_context_registry") as registry:
            registry.snapshot_current_page.return_value = snapshot
            result = DouyinCurrentPageCaptureService(db=SimpleNamespace()).detect_current_page(account_id)

        self.assertEqual(result.detected_page_type, "unknown_page")
        self.assertFalse(result.supported_capture)
        self.assertEqual(result.recommended_action, "open_managed_browser_profile")

    def test_capture_current_page_uses_adapter_payload_canonical_ingest_without_detached_fetch(self) -> None:
        account_id = uuid4()
        profile_id = uuid4()
        crawl_session_id = uuid4()
        db = SimpleNamespace(
            get=lambda model, identifier: SourceProfile(
                id=profile_id,
                workspace_id=uuid4(),
                source_platform=SourcePlatformEnum.DOUYIN,
                source_profile_external_id="MS4wLjABAAAAfixture-sec-uid",
                profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
                display_name="Fixture Creator",
                handle=None,
                last_crawled_at=datetime.now(UTC),
                metadata_json={},
                raw_payload_json={},
                notes=None,
            ) if model is SourceProfile else None,
            commit=lambda: None,
        )
        snapshot = SimpleNamespace(
            available=True,
            page_url="https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            title="Fixture Creator",
            body_text="Fixture profile",
            html="<html></html>",
            video_link_count=1,
            video_links=["https://www.douyin.com/video/7420000000000000001"],
            runtime_context_id="runtime-1",
            runtime_attach_status="managed_runtime_active",
            page_recovery_status="live_runtime_attached",
            managed_runtime_status="managed_runtime_active",
            reason="current_page_snapshot_captured",
        )
        ingest_summary = IngestSummary(
            crawl_session_id=str(crawl_session_id),
            status=CrawlSessionStatus.COMPLETED,
            source_profile_id=str(profile_id),
            source_platform=SourcePlatformEnum.DOUYIN,
            submitted_profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            videos_discovered_count=1,
            videos_created_count=1,
            videos_updated_count=0,
            snapshots_created_count=1,
        )
        candidate_result = SimpleNamespace(total_count=1, matched_count=1, rejected_count=0, evaluations=[object()])

        with patch("src.services.douyin_current_page_capture_service.douyin_browser_context_registry") as registry, patch(
            "src.services.douyin_current_page_capture_service.SourceIngestService"
        ) as ingest_cls, patch("src.services.douyin_current_page_capture_service.CandidateEvaluationService") as candidate_cls, patch(
            "src.services.douyin_current_page_capture_service.DouyinAccountService"
        ) as account_service_cls:
            registry.snapshot_current_page.return_value = snapshot
            account_service_cls.return_value.get_account.return_value = SimpleNamespace(id=account_id)
            account_service_cls.return_value.health_summary.return_value = SimpleNamespace(warning_summary={})
            ingest_cls.return_value.ingest_profile.return_value = ingest_summary
            candidate_cls.return_value.apply.return_value = candidate_result

            result = DouyinCurrentPageCaptureService(db=db).capture_current_page(
                account_connection_id=account_id,
                workspace_id=None,
                preset_name=None,
                filter_config=None,
                persist=True,
                max_videos=50,
            )

        ingest_call = ingest_cls.return_value.ingest_profile.call_args.kwargs
        self.assertEqual(ingest_call["profile_url"], "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(ingest_call["source_platform"], SourcePlatformEnum.DOUYIN)
        self.assertEqual(ingest_call["crawl_mode"], "operator_current_page_capture")
        self.assertIsNotNone(ingest_call["adapter_payload_json"])
        self.assertEqual(ingest_call["adapter_payload_json"]["metadata"]["fetch_execution_path"], "managed_browser_current_page")
        self.assertFalse(ingest_call["adapter_payload_json"]["metadata"]["http_fallback_attempted"])
        self.assertEqual(result.fetch_execution_path, "managed_browser_current_page")
        self.assertFalse(result.http_fallback_attempted)
        self.assertEqual(result.candidates_matched_count, 1)

    def test_capture_rejects_non_profile_pages_before_ingest(self) -> None:
        account_id = uuid4()
        snapshot = SimpleNamespace(
            available=True,
            page_url="https://www.douyin.com/video/7420000000000000001",
            title="Video",
            body_text="",
            html="<html></html>",
            video_link_count=0,
            video_links=[],
            runtime_context_id="runtime-1",
            runtime_attach_status="managed_runtime_active",
            page_recovery_status="live_runtime_attached",
            managed_runtime_status="managed_runtime_active",
            reason="current_page_snapshot_captured",
        )
        with patch("src.services.douyin_current_page_capture_service.douyin_browser_context_registry") as registry, patch(
            "src.services.douyin_current_page_capture_service.SourceIngestService"
        ) as ingest_cls, patch("src.services.douyin_current_page_capture_service.DouyinAccountService") as account_service_cls:
            registry.snapshot_current_page.return_value = snapshot
            account_service_cls.return_value.get_account.return_value = SimpleNamespace(id=account_id)
            account_service_cls.return_value.health_summary.return_value = SimpleNamespace(warning_summary={})
            with self.assertRaises(DouyinCurrentPageCaptureError) as ctx:
                DouyinCurrentPageCaptureService(db=SimpleNamespace()).capture_current_page(
                    account_connection_id=account_id,
                    workspace_id=None,
                    preset_name=None,
                    filter_config=None,
                    persist=True,
                )

        self.assertEqual(ctx.exception.code, "current_page_capture_not_supported")
        ingest_cls.assert_not_called()

    def test_capture_blocks_quarantined_profile_before_page_snapshot(self) -> None:
        account_id = uuid4()
        with patch("src.services.douyin_current_page_capture_service.douyin_browser_context_registry") as registry, patch(
            "src.services.douyin_current_page_capture_service.SourceIngestService"
        ) as ingest_cls, patch("src.services.douyin_current_page_capture_service.DouyinAccountService") as account_service_cls:
            account_service_cls.return_value.get_account.return_value = SimpleNamespace(id=account_id)
            account_service_cls.return_value.health_summary.return_value = SimpleNamespace(
                warning_summary={"profile_quarantine_state": "quarantined"}
            )

            with self.assertRaises(DouyinCurrentPageCaptureError) as ctx:
                DouyinCurrentPageCaptureService(db=SimpleNamespace()).capture_current_page(
                    account_connection_id=account_id,
                    workspace_id=None,
                    preset_name=None,
                    filter_config=None,
                    persist=True,
                )

        self.assertEqual(ctx.exception.code, "profile_quarantined")
        self.assertEqual(ctx.exception.stage, "profile_quarantine_gate")
        registry.snapshot_current_page.assert_not_called()
        ingest_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
