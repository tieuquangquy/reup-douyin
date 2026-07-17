from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.adapters.types import IngestSummary
from src.enums import CapturedItemStatus, CrawlSessionStatus, IntakeEvaluationStatus, SourcePlatformEnum
from src.models.capture_inbox import CapturedItem, CaptureSession
from src.schemas.capture_inbox import CaptureInboxAdvancedFilterRequest, CapturedItemResponse
from src.schemas.douyin_extension import (
    DouyinExtensionCaptureSessionRequest,
    DouyinExtensionCaptureRequest,
    DouyinExtensionDetectPageRequest,
    DouyinExtensionFullModalHarvestItemPayload,
    DouyinExtensionFullModalHarvestProgress,
    DouyinExtensionFullModalHarvestRequest,
    DouyinExtensionHarvestPlanProfileCardEvidence,
    DouyinExtensionHarvestPlanRequest,
    DouyinExtensionPageSnapshot,
    DouyinExtensionProfilePayload,
    DouyinExtensionRawDomDetailMetrics,
    DouyinExtensionRawEvidenceSummary,
    DouyinExtensionTargetClassificationRequest,
    DouyinExtensionTargetClassificationTarget,
    DouyinExtensionVideoPayload,
)
from src.services.capture_inbox_service import CAPTURE_INBOX_ROUTE, CAPTURE_INBOX_CRAWL_MODE, CaptureInboxError, CaptureInboxItemFailureSummary, CaptureInboxRuntimeError, CaptureInboxService, _context_mismatch_codes, _suspicious_duplicate_payload_mapping_count, _thumbnail_url_from_payload, _warning_codes_for_stage
from src.services.douyin_extension_capture_service import (
    EXTENSION_FETCH_PATH,
    DouyinExtensionCaptureError,
    DouyinExtensionCaptureService,
    isDouyinCaptureItemMetadataComplete,
)


PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid"


class IncrementalScanDb:
    def __init__(self, existing: dict[str, SimpleNamespace] | None = None):
        self.existing = existing or {}
        self.committed = False

    def scalar(self, stmt):
        text = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        for aweme_id, item in self.existing.items():
            if f"'{aweme_id}'" in text:
                return item
        return None

    def commit(self):
        self.committed = True


class FinalizedOnlyDb:
    def __init__(self):
        self.added: list[CapturedItem] = []
        self.flushed = False
        self.committed = False

    def scalar(self, _stmt):
        return None

    def scalars(self, _stmt):
        return SimpleNamespace(first=lambda: None)

    def add(self, item: CapturedItem) -> None:
        self.added.append(item)

    def flush(self) -> None:
        self.flushed = True

    def commit(self) -> None:
        self.committed = True


class DouyinExtensionCaptureServiceTests(unittest.TestCase):
    def _harvest_plan_request(self, *, videos: list[DouyinExtensionVideoPayload], harvest_mode: str = "new_and_incomplete") -> DouyinExtensionHarvestPlanRequest:
        return DouyinExtensionHarvestPlanRequest(
            capture_id="phase17a-plan-fixture",
            captured_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=len(videos)),
            profile=DouyinExtensionProfilePayload(sec_uid="MS4wLjABAAAAfixture-sec-uid", display_name="Fixture Creator"),
            capture_context={"page_url": PROFILE_URL},
            videos=videos,
            harvest_mode=harvest_mode,
        )

    def _finalized_payload(self, *, aweme_id: str = "7420000000000000001", duration_seconds: float | None = 12) -> DouyinExtensionFullModalHarvestItemPayload:
        return DouyinExtensionFullModalHarvestItemPayload(
            aweme_id=aweme_id,
            source_url=f"https://www.douyin.com/video/{aweme_id}",
            target_aweme_id=aweme_id,
            modal_aweme_id_before_extract=aweme_id,
            modal_aweme_id_after_extract=aweme_id,
            extracted_aweme_id=aweme_id,
            data_integrity_status="ok",
            raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(
                duration_seconds=duration_seconds,
                duration_text="00:12" if duration_seconds is not None else None,
                like_count=1,
                comment_count=2,
                favorite_count=3,
                share_count=4,
                posted_text="昨天",
                extraction_source="calibrated_point_dom",
                confidence="high",
            ),
            raw_detail_aweme=None,
            raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                has_dom_detail_metrics=True,
                dom_detail_metric_keys=["duration_seconds", "like_count", "comment_count", "favorite_count", "share_count", "posted_text"],
                evidence_sources=["calibrated_point_modal_counts", "full_modal_auto_harvest", "profile_card_evidence"],
                evidence_collection_version="phase17a_finalized_only_harvest",
            ),
            profile_card_evidence=DouyinExtensionHarvestPlanProfileCardEvidence(
                aweme_id=aweme_id,
                source_url=f"https://www.douyin.com/video/{aweme_id}",
                title="Finalized profile-card title",
                thumbnail_url="https://p3.douyinpic.com/obj/finalized-thumbnail",
                posted_text="昨天",
            ),
        )

    def _finalized_request(self, *, session_id, payloads: list[DouyinExtensionFullModalHarvestItemPayload]) -> DouyinExtensionFullModalHarvestRequest:
        return DouyinExtensionFullModalHarvestRequest(
            capture_session_id=session_id,
            started_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="video_detail_page"),
            capture_context={"page_url": PROFILE_URL},
            items=payloads,
            progress=DouyinExtensionFullModalHarvestProgress(
                running=False,
                target_count=len(payloads),
                current_aweme_id=payloads[-1].aweme_id if payloads else None,
                harvested_count=len(payloads),
                updated_count=0,
                duplicate_count=0,
                failed_count=0,
                flushed_count=len(payloads),
                last_error=None,
                stopped_reason="target_count_reached",
            ),
            commit_policy="finalized_only",
        )

    def test_harvest_plan_new_aweme_returns_new_without_visible_rows(self) -> None:
        db = SimpleNamespace(scalar=Mock(return_value=None), add=Mock(), commit=Mock())
        request = self._harvest_plan_request(videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001", source_video_url="https://www.douyin.com/video/7420000000000000001", desc="New card", thumbnail_url="https://p3.douyinpic.com/obj/thumb")])

        result = DouyinExtensionCaptureService(db=db).create_harvest_plan(request)

        self.assertEqual(result.new_aweme_ids, ["7420000000000000001"])
        self.assertEqual(result.target_aweme_ids, ["7420000000000000001"])
        self.assertEqual(result.created_visible_item_count, 0)
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_harvest_plan_repeated_scan_is_idempotent_without_duplicate_rows(self) -> None:
        db = SimpleNamespace(scalar=Mock(return_value=None), add=Mock(), commit=Mock())
        request = self._harvest_plan_request(videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001", source_video_url="https://www.douyin.com/video/7420000000000000001")])
        service = DouyinExtensionCaptureService(db=db)

        first = service.create_harvest_plan(request)
        second = service.create_harvest_plan(request)

        self.assertEqual(first.target_aweme_ids, second.target_aweme_ids)
        self.assertEqual(first.created_visible_item_count, 0)
        self.assertEqual(second.created_visible_item_count, 0)
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_harvest_plan_classifies_complete_existing_not_targeted_by_default(self) -> None:
        complete = SimpleNamespace(source_video_external_id="complete", duration_seconds=10, posted_at=None, metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"})
        request = self._harvest_plan_request(videos=[DouyinExtensionVideoPayload(aweme_id="complete")])

        result = DouyinExtensionCaptureService(db=IncrementalScanDb({"complete": complete})).create_harvest_plan(request)

        self.assertEqual(result.complete_aweme_ids, ["complete"])
        self.assertEqual(result.target_aweme_ids, [])

    def test_harvest_plan_incomplete_existing_is_targeted_by_default(self) -> None:
        incomplete = SimpleNamespace(source_video_external_id="incomplete", duration_seconds=None, metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"})
        request = self._harvest_plan_request(videos=[DouyinExtensionVideoPayload(aweme_id="incomplete")])

        result = DouyinExtensionCaptureService(db=IncrementalScanDb({"incomplete": incomplete})).create_harvest_plan(request)

        self.assertEqual(result.incomplete_aweme_ids, ["incomplete"])
        self.assertEqual(result.target_aweme_ids, ["incomplete"])

    def test_harvest_plan_modes_select_new_only_or_refresh_all_targets(self) -> None:
        complete = SimpleNamespace(source_video_external_id="complete", duration_seconds=10, posted_at=None, metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"})
        incomplete = SimpleNamespace(source_video_external_id="incomplete", duration_seconds=None, metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"})
        videos = [DouyinExtensionVideoPayload(aweme_id="new"), DouyinExtensionVideoPayload(aweme_id="incomplete"), DouyinExtensionVideoPayload(aweme_id="complete")]
        service = DouyinExtensionCaptureService(db=IncrementalScanDb({"complete": complete, "incomplete": incomplete}))

        new_only = service.create_harvest_plan(self._harvest_plan_request(videos=videos, harvest_mode="new_only"))
        refresh_all = service.create_harvest_plan(self._harvest_plan_request(videos=videos, harvest_mode="refresh_all"))

        self.assertEqual(new_only.target_aweme_ids, ["new"])
        self.assertEqual(refresh_all.target_aweme_ids, ["new", "incomplete", "complete"])

    def test_incremental_scan_classifies_new_aweme_ids_as_new(self) -> None:
        items = [SimpleNamespace(source_video_external_id="new-1", status=CapturedItemStatus.READY, existing_source_video_id=None)]

        result = DouyinExtensionCaptureService(db=IncrementalScanDb())._build_incremental_scan_summary(items)

        self.assertEqual(result["new_aweme_ids"], ["new-1"])
        self.assertEqual(result["target_aweme_ids"], ["new-1"])

    def test_incremental_scan_classifies_complete_existing_item_complete(self) -> None:
        existing = SimpleNamespace(
            source_video_external_id="done-1",
            duration_seconds=12,
            posted_at=datetime.now(UTC),
            metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4},
        )

        result = DouyinExtensionCaptureService(db=IncrementalScanDb({"done-1": existing}))._build_incremental_scan_summary(
            [SimpleNamespace(source_video_external_id="done-1", status=CapturedItemStatus.DUPLICATE, existing_source_video_id=uuid4())]
        )

        self.assertEqual(result["complete_aweme_ids"], ["done-1"])
        self.assertEqual(result["target_aweme_ids"], [])

    def test_incremental_scan_existing_missing_duration_is_incomplete(self) -> None:
        existing = SimpleNamespace(source_video_external_id="miss-duration", duration_seconds=None, metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"})

        result = DouyinExtensionCaptureService(db=IncrementalScanDb({"miss-duration": existing}))._build_incremental_scan_summary(
            [SimpleNamespace(source_video_external_id="miss-duration", status=CapturedItemStatus.DUPLICATE, existing_source_video_id=uuid4())]
        )

        self.assertEqual(result["incomplete_aweme_ids"], ["miss-duration"])

    def test_incremental_scan_existing_missing_engagement_is_incomplete(self) -> None:
        existing = SimpleNamespace(source_video_external_id="miss-like", duration_seconds=10, posted_at=datetime.now(UTC), metadata_json={"like_count": None, "comment_count": 2, "favorite_count": 3, "share_count": 4})

        result = DouyinExtensionCaptureService(db=IncrementalScanDb({"miss-like": existing}))._build_incremental_scan_summary(
            [SimpleNamespace(source_video_external_id="miss-like", status=CapturedItemStatus.DUPLICATE, existing_source_video_id=uuid4())]
        )

        self.assertEqual(result["incomplete_aweme_ids"], ["miss-like"])

    def test_incremental_scan_modes_build_expected_targets_and_skip_duplicates(self) -> None:
        complete = SimpleNamespace(source_video_external_id="complete", duration_seconds=10, posted_at=datetime.now(UTC), metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4})
        incomplete = SimpleNamespace(source_video_external_id="incomplete", duration_seconds=None, metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"})
        items = [
            SimpleNamespace(source_video_external_id="new", status=CapturedItemStatus.READY, existing_source_video_id=None),
            SimpleNamespace(source_video_external_id="incomplete", status=CapturedItemStatus.DUPLICATE, existing_source_video_id=uuid4()),
            SimpleNamespace(source_video_external_id="complete", status=CapturedItemStatus.DUPLICATE, existing_source_video_id=uuid4()),
            SimpleNamespace(source_video_external_id="new", status=CapturedItemStatus.DUPLICATE, existing_source_video_id=None),
        ]
        service = DouyinExtensionCaptureService(db=IncrementalScanDb({"complete": complete, "incomplete": incomplete}))

        default_result = service._build_incremental_scan_summary(items, harvest_mode="new_and_incomplete")
        new_only_result = service._build_incremental_scan_summary(items, harvest_mode="new_only")
        refresh_all_result = service._build_incremental_scan_summary(items, harvest_mode="refresh_all")

        self.assertEqual(default_result["target_aweme_ids"], ["new", "incomplete"])
        self.assertEqual(new_only_result["target_aweme_ids"], ["new"])
        self.assertEqual(refresh_all_result["target_aweme_ids"], ["new", "incomplete", "complete"])
        self.assertEqual(default_result["skipped_aweme_ids"], ["new"])

    def test_metadata_complete_helper_does_not_require_view_count(self) -> None:
        item = SimpleNamespace(source_video_external_id="complete-no-view", duration_seconds=12, posted_at=None, metadata_json={"posted_text": "昨天", "like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "view_count": None})

        self.assertTrue(isDouyinCaptureItemMetadataComplete(item))

    def test_detect_page_classifies_real_browser_profile_payload(self) -> None:
        request = DouyinExtensionDetectPageRequest(
            page=DouyinExtensionPageSnapshot(
                url=PROFILE_URL,
                title="Fixture Creator",
                body_text_sample="Fixture profile",
                video_link_count=2,
            )
        )

        result = DouyinExtensionCaptureService(db=SimpleNamespace()).detect_page(request)

        self.assertEqual(result.detected_page_type, "profile_feed_page")
        self.assertTrue(result.supported_capture)
        self.assertEqual(result.normalized_profile_url, PROFILE_URL)
        self.assertEqual(result.recommended_action, "capture_current_page")

    def test_detect_page_rejects_secret_like_payload_keys(self) -> None:
        request = DouyinExtensionDetectPageRequest(
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL),
            diagnostics={"cookie": "sessionid=secret"},
        )

        with self.assertRaises(DouyinExtensionCaptureError) as ctx:
            DouyinExtensionCaptureService(db=SimpleNamespace()).detect_page(request)

        self.assertEqual(ctx.exception.code, "extension_payload_contains_secret_field")
        self.assertEqual(ctx.exception.stage, "detect_page")

    def test_video_payload_preserves_card_grid_metadata_for_staging(self) -> None:
        payload = DouyinExtensionVideoPayload(
            aweme_id="7420000000000000001",
            thumbnail_url="https://p3.douyinpic.com/obj/example-thumbnail",
            poster_url="https://p3.douyinpic.com/obj/example-poster",
            cover={"url_list": ["https://p3.douyinpic.com/obj/example-cover"]},
            url_list=["https://p3.douyinpic.com/obj/example-list"],
            thumbnail_source_type="img.getAttribute(data-src)",
            thumbnail_source_types=["img.getAttribute(data-src)", "computed.backgroundImage"],
            thumbnail_source="network_json",
            thumbnail_missing_reason=None,
            posted_source="detail_hydrate",
            duration_source="detail_hydrate",
            view_count_source="network_json",
            like_count_source="network_json",
            comment_count_source="dom_fallback",
            share_count_source="fallback_none",
            engagement_rate_source="derived_from_counts",
            has_speech=None,
            text_density=None,
            has_heavy_watermark=None,
            processing_complexity=None,
            copyright_risk=None,
            network_source="network_json",
            raw={"aweme_id": "7420000000000000001", "has_cover": True},
            raw_network_aweme={"aweme_id": "7420000000000000001", "statistics": {"play_count": 12000}},
            raw_detail_aweme={"aweme_id": "7420000000000000001", "detail": True},
            raw_dom_snapshot={"aweme_id": "7420000000000000001", "visible_text": "card-local text"},
            raw_evidence_summary={"has_network_aweme": True, "has_detail_aweme": True, "has_dom_snapshot": True},
            duration_text="01:23",
            duration_seconds=83,
            posted_text="昨天",
            view_count=12000,
            view_count_text="1.2万",
            like_count=456,
            like_count_text="456",
            comment_count=7,
            comment_count_text="7",
            poster_aspect_ratio=9 / 16,
            preview_status="ready",
            source_link_status="captured",
            media_asset_status="not_generated",
            media_status="source_link_captured",
            extraction_diagnostics={"has_card_root": True},
        )

        dumped = payload.model_dump(exclude_none=True)

        self.assertEqual(dumped["thumbnail_url"], "https://p3.douyinpic.com/obj/example-thumbnail")
        self.assertEqual(dumped["poster_url"], "https://p3.douyinpic.com/obj/example-poster")
        self.assertEqual(dumped["cover"]["url_list"], ["https://p3.douyinpic.com/obj/example-cover"])
        self.assertEqual(dumped["url_list"], ["https://p3.douyinpic.com/obj/example-list"])
        self.assertEqual(dumped["thumbnail_source_type"], "img.getAttribute(data-src)")
        self.assertEqual(dumped["thumbnail_source_types"], ["img.getAttribute(data-src)", "computed.backgroundImage"])
        self.assertEqual(dumped["thumbnail_source"], "network_json")
        self.assertNotIn("thumbnail_missing_reason", dumped)
        self.assertEqual(dumped["posted_source"], "detail_hydrate")
        self.assertEqual(dumped["duration_source"], "detail_hydrate")
        self.assertEqual(dumped["view_count_source"], "network_json")
        self.assertEqual(dumped["like_count_source"], "network_json")
        self.assertEqual(dumped["comment_count_source"], "dom_fallback")
        self.assertEqual(dumped["share_count_source"], "fallback_none")
        self.assertEqual(dumped["engagement_rate_source"], "derived_from_counts")
        self.assertNotIn("has_speech", dumped)
        self.assertNotIn("text_density", dumped)
        self.assertNotIn("has_heavy_watermark", dumped)
        self.assertNotIn("processing_complexity", dumped)
        self.assertNotIn("copyright_risk", dumped)
        self.assertEqual(dumped["network_source"], "network_json")

    def test_classify_targets_returns_new_incomplete_complete_counts(self) -> None:
        complete = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="complete-1",
            duration_seconds=12,
            posted_at=datetime.now(UTC),
            metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4},
            updated_at=datetime.now(UTC),
        )
        incomplete = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="incomplete-1",
            duration_seconds=None,
            posted_at=None,
            metadata_json={"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4, "posted_text": "昨天"},
            updated_at=datetime.now(UTC),
        )
        service = DouyinExtensionCaptureService(db=IncrementalScanDb({"complete-1": complete, "incomplete-1": incomplete}))
        request = DouyinExtensionTargetClassificationRequest(
            profile_url=PROFILE_URL,
            targets=[
                DouyinExtensionTargetClassificationTarget(aweme_id="new-1"),
                DouyinExtensionTargetClassificationTarget(aweme_id="incomplete-1"),
                DouyinExtensionTargetClassificationTarget(aweme_id="complete-1"),
            ],
        )

        response = service.classify_targets(request)

        self.assertEqual(response["counts"]["new"], 1)
        self.assertEqual(response["counts"]["incomplete"], 1)
        self.assertEqual(response["counts"]["complete"], 1)
        self.assertEqual(response["counts"]["failed"], 0)
        self.assertEqual(response["counts"]["skipped"], 0)
        self.assertEqual(response["counts"]["unknown"], 0)

    def test_video_payload_accepts_extension_dom_text_and_canonical_engagement_literals(self) -> None:
        payload = DouyinExtensionVideoPayload(
            aweme_id="7420000000000000002",
            duration_source="dom_text",
            view_count_source="dom_text",
            like_count_source="dom_text",
            comment_count_source="dom_text",
            share_count_source="fallback_none",
            engagement_rate_source="derived_from_canonical_counts",
            has_speech=None,
            text_density=None,
            has_heavy_watermark=None,
            processing_complexity=None,
            copyright_risk=None,
        )

        dumped = payload.model_dump(exclude_none=True)

        self.assertEqual(dumped["duration_source"], "dom_text")
        self.assertEqual(dumped["view_count_source"], "dom_text")
        self.assertEqual(dumped["like_count_source"], "dom_text")
        self.assertEqual(dumped["comment_count_source"], "dom_text")
        self.assertEqual(dumped["share_count_source"], "fallback_none")
        self.assertEqual(dumped["engagement_rate_source"], "derived_from_canonical_counts")
        self.assertNotIn("has_speech", dumped)
        self.assertNotIn("text_density", dumped)
        self.assertNotIn("has_heavy_watermark", dumped)
        self.assertNotIn("processing_complexity", dumped)
        self.assertNotIn("copyright_risk", dumped)

    def test_thumbnail_url_from_payload_uses_deterministic_priority(self) -> None:
        payload = {
            "cover_url": "https://p3.douyinpic.com/obj/cover",
            "poster_url": "https://p3.douyinpic.com/obj/poster",
            "url_list": ["https://p3.douyinpic.com/obj/list"],
        }

        self.assertEqual(_thumbnail_url_from_payload(payload), "https://p3.douyinpic.com/obj/poster")

    def test_thumbnail_url_from_payload_rejects_video_page_as_placeholder(self) -> None:
        payload = {"thumbnail_url": "https://www.douyin.com/video/7420000000000000001"}

        self.assertIsNone(_thumbnail_url_from_payload(payload))

    def test_thumbnail_url_from_payload_rejects_ui_chrome_assets(self) -> None:
        self.assertIsNone(_thumbnail_url_from_payload({"thumbnail_url": "https://p3.douyinpic.com/obj/getapp-banner.webp"}))
        self.assertIsNone(_thumbnail_url_from_payload({"thumbnail_url": "https://p3.douyinpic.com/obj/avatar-logo.png"}))

    def test_thumbnail_url_from_payload_promotes_douyin_tos_storage_path(self) -> None:
        raw = "https://www.douyin.com/tos-cn-p-0015/15ec77b7a8aa4c0b9d0bc116ce1dc908_1613485990"
        promoted = _thumbnail_url_from_payload({"thumbnail_url": raw})
        self.assertEqual(promoted, raw)

    def test_video_payload_accepts_missing_thumbnail_provenance(self) -> None:
        payload = DouyinExtensionVideoPayload(
            aweme_id="7420000000000000099",
            source_video_url="https://www.douyin.com/video/7420000000000000099",
            thumbnail_source="missing",
            thumbnail_missing_reason="detail_hydrate_no_cover",
            preview_status="missing",
        )

        dumped = payload.model_dump(exclude_none=True)

        self.assertEqual(dumped["thumbnail_source"], "missing")
        self.assertEqual(dumped["thumbnail_missing_reason"], "detail_hydrate_no_cover")

    def test_context_mismatch_codes_reject_cross_session_project_profile_page_and_tab(self) -> None:
        workspace_id = uuid4()
        session_context = {
            "workspace_id": str(workspace_id),
            "capture_id": "capture-current",
            "tab_id": 11,
            "page_url": PROFILE_URL,
            "page_url_normalized": PROFILE_URL,
            "profile_url": PROFILE_URL,
            "profile_external_id": "MS4wLjABAAAAfixture-sec-uid",
        }
        raw_item = {
            "capture_context": {
                "workspace_id": str(uuid4()),
                "capture_id": "capture-previous",
                "tab_id": 99,
                "page_url": "https://www.douyin.com/user/other-profile",
                "page_url_normalized": "https://www.douyin.com/user/other-profile",
                "profile_url": "https://www.douyin.com/user/other-profile",
                "profile_external_id": "other-profile",
            }
        }

        mismatch_codes = _context_mismatch_codes(session_context, raw_item, workspace_id=workspace_id)

        self.assertIn("context_mismatch", mismatch_codes)
        self.assertIn("project_mismatch", mismatch_codes)
        self.assertIn("session_mismatch", mismatch_codes)
        self.assertIn("tab_mismatch", mismatch_codes)
        self.assertIn("profile_mismatch", mismatch_codes)
        self.assertIn("page_mismatch", mismatch_codes)

    def test_context_mismatch_codes_preserve_optional_debug_reason(self) -> None:
        workspace_id = uuid4()
        session_context = {
            "workspace_id": str(workspace_id),
            "capture_id": "capture-current",
            "page_url": PROFILE_URL,
            "profile_url": PROFILE_URL,
        }
        raw_item = {
            "capture_context": {
                "workspace_id": str(workspace_id),
                "capture_id": "capture-current",
                "page_url": PROFILE_URL,
                "profile_url": PROFILE_URL,
            },
            "context_mismatch_codes": ["profile_mismatch"],
        }

        mismatch_codes = _context_mismatch_codes(session_context, raw_item, workspace_id=workspace_id)

        self.assertEqual(mismatch_codes, ["context_mismatch", "profile_mismatch"])

    def test_capture_inbox_list_items_requires_current_session_scope(self) -> None:
        with self.assertRaises(CaptureInboxError) as ctx:
            CaptureInboxService(db=SimpleNamespace()).list_items()

        self.assertEqual(ctx.exception.code, "capture_session_id_required")

    def test_capture_inbox_advanced_filter_blocks_high_complexity(self) -> None:
        service = CaptureInboxService(db=SimpleNamespace())
        item = SimpleNamespace(
            metadata_json={"processing_complexity": "high"},
            posted_at=datetime.now(UTC),
            duration_seconds=12,
        )

        matched = service._matches_advanced_filter(
            item,
            CaptureInboxAdvancedFilterRequest(exclude_high_complexity=True),
        )

        self.assertFalse(matched)

    def test_capture_inbox_advanced_filter_allows_with_opt_out_complexity_exclusion(self) -> None:
        service = CaptureInboxService(db=SimpleNamespace())
        item = SimpleNamespace(
            metadata_json={"processing_complexity": "high"},
            posted_at=datetime.now(UTC),
            duration_seconds=12,
        )

        matched = service._matches_advanced_filter(
            item,
            CaptureInboxAdvancedFilterRequest(exclude_high_complexity=False, exclude_high_processing_complexity=False),
        )

        self.assertTrue(matched)

    def test_build_item_persists_canonical_thumbnail_url(self) -> None:
        session = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), capture_id="capture-thumbnail-fixture")
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-thumbnail-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[],
        )
        raw_item = {
            "aweme_id": "7420000000000000001",
            "source_video_url": "https://www.douyin.com/video/7420000000000000001",
            "thumbnail_url": "https://p3.douyinpic.com/obj/real-grid-thumbnail",
            "url_list": ["https://p3.douyinpic.com/obj/real-grid-thumbnail"],
            "thumbnail_source_type": "img.getAttribute(data-src)",
            "thumbnail_source_types": ["img.getAttribute(data-src)"],
            "network_source": "network_json",
            "thumbnail_source": "network_json",
            "posted_source": "network_json",
            "thumbnail_missing_reason": "thumbnail_unresolved",
            "raw": {"network": "safe-summary"},
            "raw_network_aweme": {"aweme_id": "7420000000000000001", "statistics": {"play_count": 12000}},
            "raw_detail_aweme": {"aweme_id": "7420000000000000001", "detail": True},
            "raw_dom_snapshot": {"aweme_id": "7420000000000000001", "visible_text": "card-local text"},
            "raw_evidence_summary": {"has_network_aweme": True, "has_detail_aweme": True, "has_dom_snapshot": True},
            "duration_text": "00:42",
            "duration_seconds": 42,
            "posted_text": "昨天",
            "view_count": 12000,
            "view_count_text": "1.2万",
            "like_count": 456,
            "like_count_text": "456",
            "comment_count": 7,
            "comment_count_text": "7",
            "poster_aspect_ratio": 9 / 16,
            "preview_status": "pending",
            "source_link_status": "captured",
            "media_asset_status": "not_generated",
            "media_status": "pending",
        }

        item = CaptureInboxService(db=SimpleNamespace())._build_item(
            session=session,
            request=request,
            raw_item=raw_item,
            raw_item_index=0,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )

        self.assertEqual(item.thumbnail_url, "https://p3.douyinpic.com/obj/real-grid-thumbnail")
        self.assertEqual(item.preview_url, "https://p3.douyinpic.com/obj/real-grid-thumbnail")
        self.assertEqual(item.raw_payload_json["thumbnail_source_types"], ["img.getAttribute(data-src)"])
        self.assertEqual(item.duration_seconds, 42)
        self.assertEqual(item.metadata_json["duration_text"], "00:42")
        self.assertEqual(item.metadata_json["posted_text"], "昨天")
        self.assertEqual(item.metadata_json["view_count"], 12000)
        self.assertEqual(item.metadata_json["view_count_text"], "1.2万")
        self.assertNotIn("like_count", item.metadata_json)
        self.assertNotIn("comment_count", item.metadata_json)
        self.assertEqual(item.metadata_json["poster_aspect_ratio"], 9 / 16)
        self.assertEqual(item.metadata_json["preview_status"], "ready")
        self.assertEqual(item.metadata_json["requested_preview_status"], "pending")
        self.assertEqual(item.metadata_json["source_link_status"], "captured")
        self.assertEqual(item.metadata_json["requested_source_link_status"], "captured")
        self.assertEqual(item.metadata_json["media_asset_status"], "not_generated")
        self.assertEqual(item.metadata_json["requested_media_asset_status"], "not_generated")
        self.assertEqual(item.metadata_json["media_status"], "source_link_captured")
        self.assertEqual(item.metadata_json["requested_media_status"], "pending")
        self.assertEqual(item.metadata_json["thumbnail_source_type"], "img.getAttribute(data-src)")
        self.assertEqual(item.metadata_json["thumbnail_source_types"], ["img.getAttribute(data-src)"])
        self.assertEqual(item.metadata_json["network_source"], "network_json")
        self.assertEqual(item.metadata_json["thumbnail_source"], "network_json")
        self.assertEqual(item.metadata_json["thumbnail_missing_reason"], "thumbnail_unresolved")
        self.assertEqual(item.metadata_json["posted_source"], "existing_canonical")
        self.assertEqual(item.metadata_json["metadata_status"], "complete")
        self.assertEqual(item.metadata_json["time_status"], "captured")
        self.assertEqual(item.metadata_json["performance_status"], "captured")
        self.assertEqual(item.metadata_json["processing_fit_status"], "captured")
        self.assertEqual(item.metadata_json["raw"], {"network": "safe-summary"})
        self.assertEqual(item.metadata_json["raw_network_aweme"]["aweme_id"], "7420000000000000001")
        self.assertEqual(item.metadata_json["raw_detail_aweme"]["aweme_id"], "7420000000000000001")
        self.assertEqual(item.metadata_json["raw_dom_snapshot"]["aweme_id"], "7420000000000000001")
        self.assertTrue(item.metadata_json["raw_evidence_summary"]["has_network_aweme"])

    def test_build_item_preserves_missing_thumbnail_reason_without_placeholder(self) -> None:
        session = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), capture_id="capture-missing-thumbnail-fixture")
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-missing-thumbnail-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[],
        )
        raw_item = {
            "aweme_id": "7420000000000000099",
            "source_video_url": "https://www.douyin.com/video/7420000000000000099",
            "thumbnail_source": "missing",
            "thumbnail_missing_reason": "detail_hydrate_no_cover",
            "extraction_diagnostics": {"thumbnail_missing_reason": "detail_hydrate_no_cover"},
            "preview_status": "missing",
            "source_link_status": "captured",
            "media_asset_status": "not_generated",
        }

        item = CaptureInboxService(db=SimpleNamespace())._build_item(
            session=session,
            request=request,
            raw_item=raw_item,
            raw_item_index=0,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )

        self.assertIsNone(item.thumbnail_url)
        self.assertIsNone(item.preview_url)
        self.assertEqual(item.metadata_json["thumbnail_source"], "missing")
        self.assertEqual(item.metadata_json["thumbnail_missing_reason"], "detail_hydrate_no_cover")
        self.assertEqual(item.metadata_json["extraction_diagnostics"], {"thumbnail_missing_reason": "detail_hydrate_no_cover"})
        self.assertEqual(item.metadata_json["preview_status"], "missing")

    def test_build_item_and_response_preserve_zero_canonical_stats(self) -> None:
        session = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), capture_id="capture-zero-stats-fixture")
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-zero-stats-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[],
        )
        raw_item = {
            "aweme_id": "7420000000000000003",
            "source_video_url": "https://www.douyin.com/video/7420000000000000003",
            "thumbnail_url": "https://p3.douyinpic.com/obj/zero-stats-thumbnail",
            "duration_seconds": 0,
            "duration_text": "00:00",
            "posted_text": "刚刚",
            "view_count": 0,
            "like_count": 0,
            "comment_count": 0,
            "statistics": {
                "play_count": 999,
                "digg_count": 888,
                "comment_count": 777,
            },
            "preview_status": "ready",
            "source_link_status": "captured",
            "media_asset_status": "not_generated",
            "media_status": "source_link_captured",
        }

        item = CaptureInboxService(db=SimpleNamespace())._build_item(
            session=session,
            request=request,
            raw_item=raw_item,
            raw_item_index=0,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )
        item.id = uuid4()
        item.created_at = datetime.now(UTC)
        item.updated_at = datetime.now(UTC)
        item.intake_evaluation_status = IntakeEvaluationStatus.NOT_EVALUATED

        response = CapturedItemResponse.model_validate(item)

        self.assertEqual(item.duration_seconds, 0)
        self.assertEqual(item.metadata_json["duration_seconds"], 0)
        self.assertEqual(item.metadata_json["view_count"], 0)
        self.assertEqual(item.metadata_json["like_count"], 0)
        self.assertEqual(item.metadata_json["comment_count"], 0)
        self.assertEqual(item.raw_payload_json["statistics"]["view_count"], 0)
        self.assertEqual(item.raw_payload_json["statistics"]["like_count"], 0)
        self.assertEqual(item.raw_payload_json["statistics"]["comment_count"], 0)
        self.assertEqual(response.aweme_id, "7420000000000000003")
        self.assertEqual(response.thumbnail_url, "https://p3.douyinpic.com/obj/zero-stats-thumbnail")
        self.assertEqual(response.duration_seconds, 0)
        self.assertEqual(response.duration_text, "00:00")
        self.assertEqual(response.posted_text_raw, "刚刚")
        self.assertEqual(response.posted_text, response.posted_display)
        self.assertIsNotNone(response.posted_display)
        self.assertEqual(response.view_count, 0)
        self.assertEqual(response.like_count, 0)
        self.assertEqual(response.comment_count, 0)
        self.assertEqual(response.preview_status, "ready")
        self.assertEqual(response.source_link_status, "captured")
        self.assertEqual(response.media_asset_status, "not_generated")
        self.assertEqual(response.media_status, "source_link_captured")

    def test_build_item_and_response_expose_provenance_and_processing_fit_semantics(self) -> None:
        session = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), capture_id="capture-processing-fit-fixture")
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-processing-fit-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[],
        )
        raw_item = {
            "aweme_id": "7420000000000000777",
            "source_video_url": "https://www.douyin.com/video/7420000000000000777",
            "thumbnail_url": "https://p3.douyinpic.com/obj/processing-fit-thumbnail",
            "duration_seconds": 12,
            "view_count": 123,
            "like_count": 45,
            "comment_count": 6,
            "share_count": 7,
            "engagement_rate": 0.47,
            "posted_source": "detail_hydrate",
            "duration_source": "dom_text",
            "view_count_source": "dom_text",
            "like_count_source": "network_json",
            "comment_count_source": "dom_text",
            "share_count_source": "dom_text",
            "engagement_rate_source": "derived_from_canonical_counts",
            "has_speech": None,
            "text_density": None,
            "has_heavy_watermark": None,
            "processing_complexity": None,
            "copyright_risk": None,
            "preview_status": "ready",
            "source_link_status": "captured",
            "media_asset_status": "not_generated",
            "media_status": "source_link_captured",
        }

        item = CaptureInboxService(db=SimpleNamespace())._build_item(
            session=session,
            request=request,
            raw_item=raw_item,
            raw_item_index=0,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )
        item.id = uuid4()
        item.created_at = datetime.now(UTC)
        item.updated_at = datetime.now(UTC)
        item.intake_evaluation_status = IntakeEvaluationStatus.NOT_EVALUATED

        self.assertIn("has_speech", item.metadata_json)
        self.assertIn("text_density", item.metadata_json)
        self.assertIn("has_heavy_watermark", item.metadata_json)
        self.assertIn("processing_complexity", item.metadata_json)
        self.assertIn("copyright_risk", item.metadata_json)
        self.assertIsNone(item.metadata_json["has_speech"])
        self.assertIsNone(item.metadata_json["text_density"])
        self.assertIsNone(item.metadata_json["has_heavy_watermark"])
        self.assertIsNone(item.metadata_json["processing_complexity"])
        self.assertIsNone(item.metadata_json["copyright_risk"])
        self.assertEqual(item.metadata_json["posted_source"], "missing")
        self.assertEqual(item.metadata_json["duration_source"], "existing_canonical")
        self.assertEqual(item.metadata_json["view_count_source"], "existing_canonical")
        self.assertEqual(item.metadata_json["like_count_source"], "existing_canonical")
        self.assertEqual(item.metadata_json["comment_count_source"], "existing_canonical")
        self.assertEqual(item.metadata_json["share_count_source"], "existing_canonical")
        self.assertEqual(item.metadata_json["engagement_rate_source"], "existing_canonical")

        response = CapturedItemResponse.model_validate(item)

        self.assertEqual(response.posted_source, "missing")
        self.assertEqual(response.duration_source, "existing_canonical")
        self.assertEqual(response.view_count_source, "existing_canonical")
        self.assertEqual(response.like_count_source, "existing_canonical")
        self.assertEqual(response.comment_count_source, "existing_canonical")
        self.assertEqual(response.share_count_source, "existing_canonical")
        self.assertEqual(response.engagement_rate_source, "existing_canonical")
        self.assertIsNone(response.has_speech)
        self.assertIsNone(response.text_density)
        self.assertIsNone(response.has_heavy_watermark)
        self.assertIsNone(response.processing_complexity)
        self.assertIsNone(response.copyright_risk)

    def test_suspicious_duplicate_payload_mapping_warns_for_distinct_network_ids_sharing_same_metadata(self) -> None:
        session = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), capture_id="capture-fanout-fixture")
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-fanout-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=2),
            videos=[],
        )
        service = CaptureInboxService(db=SimpleNamespace())
        first = service._build_item(
            session=session,
            request=request,
            raw_item={
                "aweme_id": "7420000000000000101",
                "source_video_url": "https://www.douyin.com/video/7420000000000000101",
                "thumbnail_url": "https://p3.douyinpic.com/obj/shared-network-cover",
                "posted_at": "2026-04-27T10:30:00.000Z",
                "view_count": 100,
                "like_count": 20,
                "comment_count": 3,
                "network_source": "network_json",
                "thumbnail_source": "network_json",
                "posted_source": "network_json",
            },
            raw_item_index=0,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )
        second = service._build_item(
            session=session,
            request=request,
            raw_item={
                "aweme_id": "7420000000000000102",
                "source_video_url": "https://www.douyin.com/video/7420000000000000102",
                "thumbnail_url": "https://p3.douyinpic.com/obj/shared-network-cover",
                "posted_at": "2026-04-27T10:30:00.000Z",
                "view_count": 100,
                "like_count": 20,
                "comment_count": 3,
                "network_source": "network_json",
                "thumbnail_source": "network_json",
                "posted_source": "network_json",
            },
            raw_item_index=1,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )

        self.assertEqual(_suspicious_duplicate_payload_mapping_count([first, second]), 1)
        warning_session = SimpleNamespace(duplicate_item_count=0, ready_item_count=2, captured_item_count=2)
        self.assertIn(
            "suspicious_duplicate_payload_mapping",
            _warning_codes_for_stage(warning_session, [], suspicious_duplicate_payload_mapping_count=1),
        )
        self.assertEqual(first.source_video_external_id, "7420000000000000101")
        self.assertEqual(second.source_video_external_id, "7420000000000000102")
        self.assertEqual(first.metadata_json["thumbnail_source"], "network_json")
        self.assertEqual(second.metadata_json["posted_source"], "existing_canonical")

    def test_build_item_keeps_preview_and_media_missing_when_assets_are_absent(self) -> None:
        session = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), capture_id="capture-missing-fixture")
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-missing-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[],
        )
        raw_item = {
            "aweme_id": "7420000000000000002",
            "preview_status": "ready",
            "source_link_status": "captured",
            "media_asset_status": "ready",
            "media_status": "ready",
        }

        item = CaptureInboxService(db=SimpleNamespace())._build_item(
            session=session,
            request=request,
            raw_item=raw_item,
            raw_item_index=0,
            profile_url=PROFILE_URL,
            profile_external_id="MS4wLjABAAAAfixture-sec-uid",
        )

        self.assertIsNone(item.thumbnail_url)
        self.assertIsNone(item.preview_url)
        self.assertIsNone(item.source_url)
        self.assertEqual(item.metadata_json["preview_status"], "missing")
        self.assertEqual(item.metadata_json["requested_preview_status"], "ready")
        self.assertEqual(item.metadata_json["source_link_status"], "missing")
        self.assertEqual(item.metadata_json["requested_source_link_status"], "captured")
        self.assertEqual(item.metadata_json["media_asset_status"], "not_generated")
        self.assertEqual(item.metadata_json["requested_media_asset_status"], "ready")
        self.assertEqual(item.metadata_json["media_status"], "missing")
        self.assertEqual(item.metadata_json["requested_media_status"], "ready")

    def test_capture_current_page_stages_capture_inbox_without_canonical_promotion(self) -> None:
        capture_session_id = uuid4()
        db = SimpleNamespace()
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-fixture",
            captured_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(
                url=PROFILE_URL,
                title="Fixture Creator",
                profile_url=PROFILE_URL,
                video_link_count=1,
            ),
            profile=DouyinExtensionProfilePayload(sec_uid="MS4wLjABAAAAfixture-sec-uid", display_name="Fixture Creator"),
            videos=[
                DouyinExtensionVideoPayload(
                    aweme_id="7420000000000000001",
                    source_video_url="https://www.douyin.com/video/7420000000000000001",
                    desc="Fixture video",
                    statistics={"like_count": 1200, "comment_count": 12},
                )
            ],
            persist=True,
        )
        session = SimpleNamespace(
            id=capture_session_id,
            capture_id="capture-fixture",
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            visible_item_count=1,
            captured_item_count=1,
            normalized_item_count=1,
            duplicate_item_count=0,
            ready_item_count=1,
            skipped_item_count=0,
            promoted_item_count=0,
            candidate_created_count=0,
            failed_item_count=0,
        )
        stage_result = SimpleNamespace(
            session=session,
            items=[SimpleNamespace(id=uuid4())],
            failure_summaries=[],
            warning_codes=[],
            stage="capture_session_staged",
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.return_value = stage_result

            result = DouyinExtensionCaptureService(db=db).capture_current_page(request, filter_config=None)

        stage_call = inbox_cls.return_value.stage_extension_capture.call_args.kwargs
        self.assertEqual(stage_call["profile_url"], PROFILE_URL)
        self.assertEqual(stage_call["detected_page_type"], "profile_feed_page")
        self.assertEqual(result.capture_session_id, capture_session_id)
        self.assertIsNone(result.source_profile_id)
        self.assertIsNone(result.crawl_session_id)
        self.assertEqual(result.captured_item_count, 1)
        self.assertEqual(result.ready_item_count, 1)
        self.assertEqual(result.candidate_created_count, 0)
        self.assertEqual(result.candidates_matched_count, 0)
        self.assertEqual(result.next_suggested_route, CAPTURE_INBOX_ROUTE)
        self.assertEqual(result.fetch_execution_path, EXTENSION_FETCH_PATH)
        self.assertEqual(result.stage, "capture_session_staged")
        self.assertEqual(result.submitted_count, 1)
        self.assertEqual(result.staged_count, 1)
        self.assertEqual(result.failed_count, 0)

    def test_capture_current_page_returns_partial_success_for_malformed_items(self) -> None:
        capture_session_id = uuid4()
        db = SimpleNamespace()
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-partial-fixture",
            captured_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(
                url=PROFILE_URL,
                title="Fixture Creator",
                profile_url=PROFILE_URL,
                video_link_count=2,
            ),
            profile=DouyinExtensionProfilePayload(sec_uid="MS4wLjABAAAAfixture-sec-uid", display_name="Fixture Creator"),
            videos=[
                DouyinExtensionVideoPayload(
                    aweme_id="7420000000000000001",
                    source_video_url="https://www.douyin.com/video/7420000000000000001",
                    desc="Ready fixture video",
                ),
                DouyinExtensionVideoPayload(desc="Malformed visible card without URL or id"),
            ],
            persist=True,
        )
        session = SimpleNamespace(
            id=capture_session_id,
            capture_id="capture-partial-fixture",
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            visible_item_count=2,
            captured_item_count=2,
            normalized_item_count=1,
            duplicate_item_count=0,
            ready_item_count=1,
            skipped_item_count=0,
            promoted_item_count=0,
            candidate_created_count=0,
            failed_item_count=1,
        )
        failure = CaptureInboxItemFailureSummary(
            stage="item_normalization_partial_failure",
            item_index=1,
            code="item_missing_video_identity",
            message="Captured item is missing both video URL and external id.",
        )
        stage_result = SimpleNamespace(
            session=session,
            items=[SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())],
            failure_summaries=[failure],
            warning_codes=["partial_item_failures"],
            stage="item_normalization_partial_failure",
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.return_value = stage_result

            result = DouyinExtensionCaptureService(db=db).capture_current_page(request, filter_config=None)

        self.assertTrue(result.success)
        self.assertEqual(result.capture_session_id, capture_session_id)
        self.assertEqual(result.stage, "item_normalization_partial_failure")
        self.assertEqual(result.warning_codes, ["partial_item_failures"])
        self.assertEqual(result.submitted_count, 2)
        self.assertEqual(result.staged_count, 2)
        self.assertEqual(result.ready_item_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.failure_summaries[0].item_index, 1)
        self.assertEqual(result.failure_summaries[0].code, "item_missing_video_identity")

    def test_capture_current_page_maps_schema_missing_to_structured_error(self) -> None:
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-schema-missing-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001")],
            persist=True,
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.side_effect = CaptureInboxRuntimeError(
                "schema_missing",
                "Capture Inbox database schema is missing required tables. Apply migrations and restart the backend on the extension API port.",
                stage="capture_inbox_schema_readiness",
                diagnostics_id="diag-schema-fixture",
            )

            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

        self.assertEqual(ctx.exception.code, "schema_missing")
        self.assertEqual(ctx.exception.stage, "capture_inbox_schema_readiness")
        self.assertIn("Apply migrations", ctx.exception.message)
        self.assertIsNotNone(ctx.exception.diagnostics_id)

    def test_capture_current_page_maps_migration_mismatch_to_structured_error(self) -> None:
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-migration-mismatch-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001")],
            persist=True,
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.side_effect = CaptureInboxRuntimeError(
                "migration_mismatch",
                "Capture Inbox database schema is behind the backend model. Missing column(s): captured_items: metadata_json.",
                stage="capture_inbox_schema_readiness",
            )

            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

        self.assertEqual(ctx.exception.code, "migration_mismatch")
        self.assertEqual(ctx.exception.stage, "capture_inbox_schema_readiness")
        self.assertIn("backend model", ctx.exception.message)

    def test_capture_current_page_maps_capture_session_persist_failure_to_structured_error(self) -> None:
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-session-persist-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001")],
            persist=True,
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.side_effect = CaptureInboxRuntimeError(
                "capture_session_persist_failed",
                "Capture Inbox could not persist the Capture Session. Check database connectivity, apply migrations, and restart the backend.",
                stage="capture_session_persist",
            )

            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

        self.assertEqual(ctx.exception.code, "capture_session_persist_failed")
        self.assertEqual(ctx.exception.stage, "capture_session_persist")
        self.assertIn("Capture Session", ctx.exception.message)

    def test_capture_current_page_maps_captured_item_persist_failure_to_structured_error(self) -> None:
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-item-persist-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001")],
            persist=True,
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.side_effect = CaptureInboxRuntimeError(
                "captured_item_persist_failed",
                "Capture Inbox could not persist one or more Captured Items. Check database connectivity and migration state.",
                stage="captured_item_persist",
            )

            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

        self.assertEqual(ctx.exception.code, "captured_item_persist_failed")
        self.assertEqual(ctx.exception.stage, "captured_item_persist")
        self.assertIn("Captured Items", ctx.exception.message)

    def test_v2_capture_session_preflight_creates_zero_visible_items_and_is_idempotent(self) -> None:
        workspace_id = uuid4()
        request = DouyinExtensionCaptureSessionRequest(
            source="whole_profile_staged_harvest_v2",
            profile_url=PROFILE_URL,
            normalized_profile_url=PROFILE_URL,
            profile_sec_uid_or_path="MS4wLjABAAAAfixture-sec-uid",
            profile_display_name="Fixture Display Name",
            profile_avatar_url="https://p1-pc-sign.douyinpic.com/profile-avatar.jpeg",
            display_title="Fixture Session Ribbon Title",
            source_modal_aweme_id="7420000000000000001",
            verified_target_count=54,
            queued_count=12,
            run_id="phase17w-run-1",
            mode="whole_profile_staged_harvest_v2",
        )
        db = SimpleNamespace(added=[], committed=False, refreshed=None, scalar=Mock(return_value=None))
        db.add = lambda value: db.added.append(value)
        db.commit = lambda: setattr(db, "committed", True)
        db.refresh = lambda value: setattr(db, "refreshed", value)

        with patch("src.services.douyin_extension_capture_service.ensure_default_workspace", return_value=SimpleNamespace(id=workspace_id)):
            result = DouyinExtensionCaptureService(db=db).create_capture_session(request)

        self.assertTrue(result.created)
        self.assertEqual(result.profile_url, PROFILE_URL)
        self.assertEqual(result.source, "whole_profile_staged_harvest_v2")
        self.assertEqual(len(db.added), 1)
        session = db.added[0]
        self.assertEqual(session.capture_id, "Fixture Session Ribbon Title")
        self.assertEqual(session.capture_source, "whole_profile_staged_harvest_v2")
        self.assertEqual(session.page_url, PROFILE_URL)
        self.assertEqual(session.page_title, "Fixture Session Ribbon Title")
        self.assertEqual(session.submitted_profile_url, PROFILE_URL)
        self.assertEqual(session.normalized_profile_identifier, "MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(session.visible_item_count, 0)
        self.assertEqual(session.captured_item_count, 0)
        self.assertEqual(session.metadata_json["run_id"], "phase17w-run-1")
        self.assertEqual(session.metadata_json["normalized_profile_url"], PROFILE_URL)
        self.assertEqual(session.metadata_json["normalized_profile_identifier"], "MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(session.metadata_json["profile_display_name"], "Fixture Display Name")
        self.assertEqual(session.metadata_json["profile_avatar_url"], "https://p1-pc-sign.douyinpic.com/profile-avatar.jpeg")
        self.assertEqual(session.metadata_json["display_title"], "Fixture Session Ribbon Title")
        self.assertEqual(session.metadata_json["expected_video_count"], 54)
        self.assertEqual(session.metadata_json["queued_count"], 12)
        self.assertEqual(session.metadata_json["created_by"], "douyin_scanner")
        self.assertEqual(session.raw_summary_json["expected_video_count"], 54)
        self.assertEqual(session.raw_summary_json["queued_count"], 12)
        self.assertEqual(session.result_summary_json["items_created_by_preflight"], 0)
        self.assertTrue(db.committed)

        db.scalar = Mock(return_value=session)
        second = DouyinExtensionCaptureService(db=db).create_capture_session(request)
        self.assertFalse(second.created)
        self.assertEqual(second.session_id, session.id)
        self.assertEqual(len(db.added), 1)

    def test_canonical_capture_session_preflight_accepts_whole_profile_harvest_and_is_idempotent(self) -> None:
        workspace_id = uuid4()
        request = DouyinExtensionCaptureSessionRequest(
            source="whole_profile_harvest",
            profile_url=PROFILE_URL,
            normalized_profile_url=PROFILE_URL,
            profile_sec_uid_or_path="MS4wLjABAAAAharvest-sec-uid",
            profile_display_name="Harvest Fixture Name",
            display_title="Harvest Session Title",
            source_modal_aweme_id=None,
            verified_target_count=55,
            queued_count=9,
            run_id="phase18j-run-1",
            mode="whole_profile_harvest",
        )
        db = SimpleNamespace(added=[], committed=False, refreshed=None, scalar=Mock(return_value=None))
        db.add = lambda value: db.added.append(value)
        db.commit = lambda: setattr(db, "committed", True)
        db.refresh = lambda value: setattr(db, "refreshed", value)

        with patch("src.services.douyin_extension_capture_service.ensure_default_workspace", return_value=SimpleNamespace(id=workspace_id)):
            result = DouyinExtensionCaptureService(db=db).create_capture_session(request)

        self.assertTrue(result.created)
        self.assertEqual(result.source, "whole_profile_harvest")
        self.assertEqual(result.run_id, "phase18j-run-1")
        self.assertEqual(len(db.added), 1)
        session = db.added[0]
        self.assertEqual(session.capture_id, "Harvest Session Title")
        self.assertEqual(session.capture_source, "whole_profile_harvest")
        self.assertEqual(session.page_url, PROFILE_URL)
        self.assertEqual(session.page_title, "Harvest Session Title")
        self.assertEqual(session.submitted_profile_url, PROFILE_URL)
        self.assertEqual(session.normalized_profile_identifier, "MS4wLjABAAAAharvest-sec-uid")
        self.assertEqual(session.visible_item_count, 0)
        self.assertEqual(session.captured_item_count, 0)
        self.assertEqual(session.metadata_json["stage"], "canonical_capture_session_created")
        self.assertEqual(session.metadata_json["profile_url"], PROFILE_URL)
        self.assertEqual(session.metadata_json["normalized_profile_url"], PROFILE_URL)
        self.assertEqual(session.metadata_json["normalized_profile_identifier"], "MS4wLjABAAAAharvest-sec-uid")
        self.assertEqual(session.metadata_json["profile_display_name"], "Harvest Fixture Name")
        self.assertEqual(session.metadata_json["display_title"], "Harvest Session Title")
        self.assertEqual(session.metadata_json["expected_video_count"], 55)
        self.assertEqual(session.metadata_json["queued_count"], 9)
        self.assertEqual(session.metadata_json["collection_mode"], "whole_profile_harvest")
        self.assertEqual(session.result_summary_json["items_created_by_preflight"], 0)

        db.scalar = Mock(return_value=session)
        second = DouyinExtensionCaptureService(db=db).create_capture_session(request)
        self.assertFalse(second.created)
        self.assertEqual(second.session_id, session.id)
        self.assertEqual(len(db.added), 1)

    def test_full_modal_harvest_uses_explicit_v2_capture_session_and_rejects_unknown_explicit_session(self) -> None:
        capture_session_id = uuid4()
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), capture_source="whole_profile_staged_harvest_v2", normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[])
        db = FinalizedOnlyDb()
        request = self._finalized_request(session_id=capture_session_id, payloads=[self._finalized_payload(aweme_id="7420000000000000101")])
        request.capture_session_source = "whole_profile_staged_harvest_v2"
        request.run_id = "phase17w-run-2"
        request.profile_url = PROFILE_URL

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session
            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)
            inbox_cls.return_value.get_session.assert_called_once_with(capture_session_id)

            inbox_cls.return_value.get_session.side_effect = Exception("missing")
            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.matched_count, 1)
        self.assertEqual(ctx.exception.code, "capture_session_not_found")
        self.assertEqual(ctx.exception.stage, "resolve_capture_session")

    def test_full_modal_harvest_resolves_v2_session_by_run_id_then_keeps_legacy_fallback(self) -> None:
        v2_session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_source="whole_profile_staged_harvest_v2",
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            submitted_profile_url=PROFILE_URL,
            items=[],
            metadata_json={},
            result_summary_json={},
            captured_item_count=0,
            ready_item_count=0,
            duplicate_item_count=0,
            failed_item_count=0,
            visible_item_count=0,
            status="pending",
            updated_at=datetime.now(UTC),
        )
        request = self._finalized_request(session_id=None, payloads=[self._finalized_payload(aweme_id="7420000000000000201")])
        request.capture_session_source = "whole_profile_staged_harvest_v2"
        request.run_id = "phase17w-run-3"
        db = FinalizedOnlyDb()
        with patch.object(DouyinExtensionCaptureService, "_find_v2_capture_session_by_run_id", return_value=v2_session):
            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)
        self.assertEqual(result.capture_session_id, v2_session.id)
        self.assertEqual(result.matched_count, 1)

        legacy_session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            submitted_profile_url=PROFILE_URL,
            items=[],
            metadata_json={},
            result_summary_json={},
            captured_item_count=0,
            ready_item_count=0,
            duplicate_item_count=0,
            failed_item_count=0,
            visible_item_count=0,
            status="pending",
            updated_at=datetime.now(UTC),
        )
        legacy_db = FinalizedOnlyDb()
        legacy_db.scalars = Mock(return_value=SimpleNamespace(first=Mock(return_value=legacy_session)))
        legacy_request = self._finalized_request(session_id=None, payloads=[self._finalized_payload(aweme_id="7420000000000000202")])
        legacy_result = DouyinExtensionCaptureService(db=legacy_db).ingest_full_modal_harvest(legacy_request)
        self.assertEqual(legacy_result.capture_session_id, legacy_session.id)

    def test_full_modal_harvest_updates_existing_item_by_exact_aweme_id(self) -> None:
        capture_session_id = uuid4()
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={"raw_dom_snapshot": {"visible_text": "Fixture DOM"}},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, items=[item])
        db = SimpleNamespace(commit=Mock())
        request = DouyinExtensionFullModalHarvestRequest(
            capture_session_id=capture_session_id,
            started_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="video_detail_page"),
            capture_context={"page_url": PROFILE_URL},
            items=[
                DouyinExtensionFullModalHarvestItemPayload(
                    aweme_id="7420000000000000001",
                    source_url="https://www.douyin.com/video/7420000000000000001",
                    target_aweme_id="7420000000000000001",
                    modal_aweme_id_before_extract="7420000000000000001",
                    modal_aweme_id_after_extract="7420000000000000001",
                    extracted_aweme_id="7420000000000000001",
                    data_integrity_status="ok",
                    metric_signature="sig:7420000000000000001:197:10:30:1",
                    raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(
                        duration_seconds=619,
                        duration_text="10:19",
                        like_count=197,
                        like_count_text="197",
                        comment_count=10,
                        comment_count_text="10",
                        favorite_count=30,
                        favorite_count_text="30",
                        share_count=1,
                        share_count_text="1",
                        posted_text="18小时前",
                        extraction_source="calibrated_point_dom",
                        confidence="high",
                    ),
                    raw_detail_aweme=None,
                    raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                        has_dom_detail_metrics=True,
                        dom_detail_metric_keys=["duration_seconds", "like_count", "comment_count", "favorite_count", "share_count", "posted_text"],
                        evidence_sources=["smart_capture_harvest", "full_modal_auto_harvest", "calibrated_point_modal_counts", "calibrated_point_dom"],
                        evidence_collection_version="phase11a_production_stabilized_calibrated_harvest",
                    ),
                )
            ],
            progress=DouyinExtensionFullModalHarvestProgress(
                running=False,
                target_count=49,
                current_aweme_id="7420000000000000001",
                harvested_count=1,
                updated_count=0,
                duplicate_count=0,
                failed_count=0,
                flushed_count=1,
                last_error=None,
                stopped_reason="target_count_reached",
            ),
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.capture_session_id, capture_session_id)
        self.assertEqual(result.matched_count, 1)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(result.unchanged_count, 0)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.duration_updated_count, 1)
        self.assertEqual(result.like_updated_count, 1)
        self.assertEqual(result.comment_updated_count, 1)
        self.assertEqual(result.favorite_updated_count, 1)
        self.assertEqual(result.share_updated_count, 1)
        self.assertEqual(item.duration_seconds, 619)
        self.assertEqual(item.metadata_json["like_count"], 197)
        self.assertEqual(item.metadata_json["comment_count"], 10)
        self.assertEqual(item.metadata_json["share_count"], 1)
        self.assertEqual(item.metadata_json["favorite_count"], 30)
        self.assertTrue(item.metadata_json["raw_evidence_summary"]["has_dom_detail_metrics"])
        self.assertEqual(item.metadata_json["raw_evidence_summary"]["evidence_collection_version"], "phase11a_production_stabilized_calibrated_harvest")
        self.assertEqual(item.metadata_json["duration_source"], "dom_detail_modal")
        self.assertEqual(item.metadata_json["like_count_source"], "dom_detail_modal")
        self.assertEqual(result.flushed_aweme_ids, ["7420000000000000001"])
        self.assertEqual(item.metadata_json["target_aweme_id"], "7420000000000000001")
        self.assertEqual(item.metadata_json["data_integrity_status"], "ok")
        inbox_cls.return_value._evaluate_items_against_intake.assert_called_once()
        inbox_cls.return_value._reconcile_session.assert_called_once_with(session)
        db.commit.assert_called_once()

    def test_full_modal_harvest_schema_accepts_calibrated_point_variants(self) -> None:
        for extraction_source in ("calibrated_point_dom", "calibrated_point_ocr", "mixed_calibrated_point"):
            payload = DouyinExtensionRawDomDetailMetrics(
                duration_seconds=10,
                like_count=5,
                comment_count=2,
                share_count=1,
                extraction_source=extraction_source,
                confidence="high",
            )
            self.assertEqual(payload.extraction_source, extraction_source)

    def test_full_modal_harvest_schema_accepts_phase10_phase11_and_phase12_transition_evidence_versions(self) -> None:
        for version in (
            "phase10a_calibrated_point_extractor",
            "phase10c_smart_capture_harvest",
            "phase11a_production_stabilized_calibrated_harvest",
            "phase12a_calibrated_five_point_workflow",
            "phase12c_recovered_four_point_harvest",
            "phase12d_four_point_navigation_loop_fix",
        ):
            payload = DouyinExtensionRawEvidenceSummary(
                has_dom_detail_metrics=True,
                dom_detail_metric_keys=["duration_seconds", "like_count"],
                evidence_sources=["calibrated_point_modal_counts", "smart_capture_harvest"],
                evidence_collection_version=version,
            )
            self.assertEqual(payload.evidence_collection_version, version)

    def test_full_modal_harvest_ignores_unmatched_aweme_ids_without_creating_duplicates(self) -> None:
        capture_session_id = uuid4()
        existing_item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, items=[existing_item])
        db = SimpleNamespace(commit=Mock())
        request = DouyinExtensionFullModalHarvestRequest(
            capture_session_id=capture_session_id,
            started_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="video_detail_page"),
            capture_context={"page_url": PROFILE_URL},
            items=[
                DouyinExtensionFullModalHarvestItemPayload(
                    aweme_id="9999999999999999999",
                    raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(extraction_source="dom_detail_modal", confidence="high", like_count=5),
                    raw_detail_aweme=None,
                    raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                        has_dom_detail_metrics=True,
                        dom_detail_metric_keys=["like_count"],
                        evidence_sources=["full_modal_auto_harvest", "dom_detail_modal"],
                        evidence_collection_version="phase6h_full_modal_auto_harvest",
                    ),
                )
            ],
            progress=DouyinExtensionFullModalHarvestProgress(
                running=False,
                target_count=49,
                current_aweme_id=None,
                harvested_count=1,
                updated_count=0,
                duplicate_count=0,
                failed_count=0,
                flushed_count=1,
                last_error=None,
                stopped_reason="no_next_video_detected",
            ),
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.matched_count, 0)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.unchanged_count, 0)
        self.assertEqual(result.unmatched_count, 1)
        self.assertEqual(result.flushed_aweme_ids, ["9999999999999999999"])
        inbox_cls.return_value._evaluate_items_against_intake.assert_not_called()
        inbox_cls.return_value._reconcile_session.assert_not_called()
        db.commit.assert_not_called()

    def test_full_modal_harvest_finalized_only_full_metadata_creates_new_item(self) -> None:
        capture_session_id = uuid4()
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[])
        db = FinalizedOnlyDb()
        payload = self._finalized_payload(aweme_id="7420000000000000002")
        payload.raw_dom_detail_metrics.posted_at = "2026-05-08T06:00:00.000Z"
        payload.raw_dom_detail_metrics.posted_display = "08/05/2026"
        payload.raw_dom_detail_metrics.posted_parse_confidence = "parsed"
        payload.profile_card_evidence.posted_at = datetime(2026, 5, 8, 6, 0, tzinfo=UTC)
        payload.profile_card_evidence.posted_text_raw = "昨天"
        payload.profile_card_evidence.posted_display = "08/05/2026"
        payload.profile_card_evidence.posted_parse_confidence = "parsed"
        request = self._finalized_request(session_id=capture_session_id, payloads=[payload])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.matched_count, 1)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].source_video_external_id, "7420000000000000002")
        self.assertEqual(db.added[0].source_url, "https://www.douyin.com/video/7420000000000000002")
        self.assertEqual(db.added[0].thumbnail_url, "https://p3.douyinpic.com/obj/finalized-thumbnail")
        self.assertEqual(db.added[0].metadata_json["posted_text"], "08/05/2026")
        self.assertEqual(db.added[0].metadata_json["posted_text_raw"], "昨天")
        self.assertEqual(db.added[0].metadata_json["posted_display"], "08/05/2026")
        self.assertEqual(db.added[0].metadata_json["posted_parse_confidence"], "parsed")
        self.assertEqual(db.added[0].status, CapturedItemStatus.READY)
        self.assertEqual(db.added[0].duration_seconds, 12)
        self.assertEqual(db.added[0].metadata_json["like_count"], 1)
        self.assertTrue(db.committed)
        self.assertEqual(result.capture_inbox_item_id, db.added[0].id)
        self.assertEqual(result.source_video_external_id, "7420000000000000002")
        self.assertEqual(result.metadata_status, "complete")
        self.assertTrue(result.item_created_or_updated)
        db.added[0].id = uuid4()
        db.added[0].created_at = datetime.now(UTC)
        db.added[0].updated_at = datetime.now(UTC)
        db.added[0].intake_evaluation_status = IntakeEvaluationStatus.MISSING_REQUIREMENTS
        response = CapturedItemResponse.model_validate(db.added[0])
        self.assertEqual(response.id, db.added[0].id)
        self.assertEqual(response.source_video_external_id, "7420000000000000002")
        self.assertEqual(response.aweme_id, "7420000000000000002")
        self.assertEqual(response.source_url, "https://www.douyin.com/video/7420000000000000002")
        self.assertEqual(response.thumbnail_url, "https://p3.douyinpic.com/obj/finalized-thumbnail")
        self.assertEqual(response.posted_text, "08/05/2026")
        self.assertEqual(response.posted_text_raw, "昨天")
        self.assertEqual(response.posted_display, "08/05/2026")
        self.assertEqual(response.metadata_status, "complete")
        inbox_cls.return_value._evaluate_items_against_intake.assert_called_once()

    def test_full_modal_harvest_finalized_only_modal_metrics_create_item_without_profile_title_or_thumbnail(self) -> None:
        capture_session_id = uuid4()
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[])
        db = FinalizedOnlyDb()
        payload = self._finalized_payload(aweme_id="7420000000000000202")
        payload.profile_card_evidence.title = None
        payload.profile_card_evidence.caption = None
        payload.profile_card_evidence.thumbnail_url = None
        payload.profile_card_evidence.cover_url = None
        payload.profile_card_evidence.poster_url = None
        request = self._finalized_request(session_id=capture_session_id, payloads=[payload])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertTrue(result.ok)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_count, 1)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].source_video_external_id, "7420000000000000202")
        self.assertEqual(result.capture_inbox_item_id, db.added[0].id)
        self.assertTrue(result.item_created_or_updated)
        db.added[0].id = uuid4()
        db.added[0].created_at = datetime.now(UTC)
        db.added[0].updated_at = datetime.now(UTC)
        db.added[0].intake_evaluation_status = IntakeEvaluationStatus.MISSING_REQUIREMENTS
        response = CapturedItemResponse.model_validate(db.added[0])
        self.assertEqual(response.source_video_external_id, "7420000000000000202")
        self.assertIsNone(response.thumbnail_url)
        self.assertEqual(response.metadata_status, "partial")

    def test_full_modal_harvest_finalized_only_missing_duration_does_not_create_item(self) -> None:
        capture_session_id = uuid4()
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[])
        db = FinalizedOnlyDb()
        request = self._finalized_request(session_id=capture_session_id, payloads=[self._finalized_payload(aweme_id="7420000000000000003", duration_seconds=None)])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.matched_count, 0)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.failure_summaries, [{"aweme_id": "7420000000000000003", "reason": "finalized_metadata_required"}])
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)
        self.assertIsNone(result.capture_inbox_item_id)
        self.assertFalse(result.item_created_or_updated)
        inbox_cls.return_value._evaluate_items_against_intake.assert_not_called()

    def test_full_modal_harvest_finalized_only_guarded_hybrid_metadata_creates_item_with_estimated_views_policy(self) -> None:
        capture_session_id = uuid4()
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[])
        db = FinalizedOnlyDb()
        aweme_id = "7420000000000000301"
        payload = DouyinExtensionFullModalHarvestItemPayload(
            aweme_id=aweme_id,
            source_video_external_id=aweme_id,
            target_aweme_id=aweme_id,
            source_url=f"https://www.douyin.com/video/{aweme_id}",
            page_url=f"https://www.douyin.com/video/{aweme_id}",
            modal_id=aweme_id,
            finalized_metadata_source="guarded_hybrid_network_cache",
            data_integrity_status="passed",
            view_count=None,
            real_view_count_available=False,
            real_view_count_data_quality="trusted_zero_only_low_confidence",
            estimated_views=4500.0,
            estimated_views_formula="tiered_like_multiplier_v1",
            estimated_views_used=True,
            real_view_count_overwritten=False,
            raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(
                duration_seconds=15,
                like_count=100,
                comment_count=2,
                favorite_count=3,
                share_count=4,
                view_count=None,
                extraction_source="page_network_cache_aweme",
                confidence="high",
            ),
            raw_detail_aweme=None,
            raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                has_network_aweme=True,
                has_dom_detail_metrics=True,
                network_keys=["statistics.digg_count"],
                dom_detail_metric_keys=["duration_seconds", "like_count", "comment_count", "favorite_count", "share_count", "view_count"],
                evidence_sources=["guarded_hybrid_collect_beta", "hybrid_network_cache_payload", "page_network_cache_aweme"],
                evidence_collection_version="phase17a_finalized_only_harvest",
            ),
            profile_card_evidence=DouyinExtensionHarvestPlanProfileCardEvidence(
                aweme_id=aweme_id,
                source_url=f"https://www.douyin.com/video/{aweme_id}",
                posted_text="昨天",
            ),
        )
        request = self._finalized_request(session_id=capture_session_id, payloads=[payload])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.matched_count, 1)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.finalized_metadata_received_count, 1)
        self.assertEqual(result.finalized_metadata_accepted_count, 1)
        self.assertEqual(result.view_count_null_received_count, 1)
        self.assertEqual(result.real_view_count_data_quality_received_count, 1)
        self.assertEqual(result.estimated_views_persisted_count, 1)
        self.assertEqual(result.accepted_not_persisted_count, 0)
        self.assertEqual(result.accepted_not_persisted_fields, [])
        self.assertEqual(result.estimated_views_accepted_but_not_persisted, "no")
        self.assertEqual(len(db.added), 1)
        self.assertNotIn("view_count", db.added[0].metadata_json)
        self.assertEqual(db.added[0].metadata_json["estimated_views"], 4500)
        self.assertIsInstance(db.added[0].metadata_json["estimated_views"], int)
        self.assertEqual(db.added[0].metadata_json["estimated_views_formula"], "tiered_like_multiplier_v1")
        self.assertEqual(db.added[0].metadata_json["real_view_count_data_quality"], "trusted_zero_only_low_confidence")
        self.assertEqual(db.added[0].metadata_json["finalized_metadata_source"], "guarded_hybrid_network_cache")

    def test_full_modal_harvest_finalized_only_guarded_hybrid_missing_required_source_url_rejects_without_mutation(self) -> None:
        capture_session_id = uuid4()
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[])
        db = FinalizedOnlyDb()
        payload = self._finalized_payload(aweme_id="7420000000000000302")
        payload.source_url = None
        payload.profile_card_evidence.source_url = None
        payload.finalized_metadata_source = "guarded_hybrid_network_cache"
        payload.raw_dom_detail_metrics.extraction_source = "exact_aweme_network_cache_object"
        payload.estimated_views = 4500
        payload.estimated_views_formula = "tiered_like_multiplier_v1"
        payload.estimated_views_used = True
        payload.real_view_count_available = False
        payload.real_view_count_data_quality = "trusted_zero_only_low_confidence"
        payload.view_count = None
        request = self._finalized_request(session_id=capture_session_id, payloads=[payload])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.failure_summaries, [{"aweme_id": "7420000000000000302", "reason": "finalized_metadata_required"}])
        self.assertEqual(result.estimated_views_persisted_count, 0)
        self.assertEqual(result.accepted_not_persisted_count, 0)
        self.assertEqual(result.estimated_views_accepted_but_not_persisted, "no")
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)
        self.assertFalse(result.item_created_or_updated)
        inbox_cls.return_value._evaluate_items_against_intake.assert_not_called()

    def test_full_modal_harvest_finalized_only_existing_incomplete_full_metadata_updates_row(self) -> None:
        capture_session_id = uuid4()
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000004",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[item])
        db = FinalizedOnlyDb()
        request = self._finalized_request(session_id=capture_session_id, payloads=[self._finalized_payload(aweme_id="7420000000000000004")])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.matched_count, 1)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(item.duration_seconds, 12)
        self.assertEqual(item.metadata_json["favorite_count"], 3)
        self.assertEqual(db.added, [])
        self.assertTrue(db.committed)

    def test_full_modal_harvest_finalized_only_unmatched_without_full_metadata_does_not_update_unrelated_item(self) -> None:
        capture_session_id = uuid4()
        unrelated_item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000005",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, workspace_id=uuid4(), normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid", submitted_profile_url=PROFILE_URL, items=[unrelated_item])
        db = FinalizedOnlyDb()
        request = self._finalized_request(session_id=capture_session_id, payloads=[self._finalized_payload(aweme_id="7420000000000000006", duration_seconds=None)])

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session

            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(unrelated_item.metadata_json, {})
        self.assertIsNone(unrelated_item.duration_seconds)
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)

    def test_full_modal_harvest_repeated_flush_is_idempotent(self) -> None:
        capture_session_id = uuid4()
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, items=[item])
        db = SimpleNamespace(commit=Mock())
        request = DouyinExtensionFullModalHarvestRequest(
            capture_session_id=capture_session_id,
            started_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="video_detail_page"),
            capture_context={"page_url": PROFILE_URL},
            items=[
                DouyinExtensionFullModalHarvestItemPayload(
                    aweme_id="7420000000000000001",
                    raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(duration_seconds=10, like_count=5, extraction_source="dom_detail_modal", confidence="high"),
                    raw_detail_aweme=None,
                    raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                        has_dom_detail_metrics=True,
                        dom_detail_metric_keys=["duration_seconds", "like_count"],
                        evidence_sources=["full_modal_auto_harvest", "dom_detail_modal"],
                        evidence_collection_version="phase6h_full_modal_auto_harvest",
                    ),
                )
            ],
            progress=DouyinExtensionFullModalHarvestProgress(
                running=False,
                target_count=49,
                current_aweme_id="7420000000000000001",
                harvested_count=1,
                updated_count=0,
                duplicate_count=0,
                failed_count=0,
                flushed_count=1,
                last_error=None,
                stopped_reason="operator_stopped",
            ),
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session
            first = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)
            second = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(first.updated_count, 1)
        self.assertTrue(first.ok)
        self.assertTrue(first.success)
        self.assertEqual(first.beta_write_effective_status, "updated_success")
        self.assertEqual(second.updated_count, 0)
        self.assertEqual(second.unchanged_count, 1)
        self.assertEqual(second.matched_count, 1)
        self.assertEqual(second.failed_count, 0)
        self.assertEqual(second.rejected_count, 0)
        self.assertTrue(second.ok)
        self.assertTrue(second.success)
        self.assertEqual(second.idempotent_unchanged_count, 1)
        self.assertEqual(second.beta_write_effective_status, "idempotent_success")
        self.assertEqual(second.accepted_unchanged_reason, "accepted_payload_already_matched_persisted_values")
        self.assertIsNone(second.code)
        self.assertEqual(second.failure_summaries, [])

    def test_full_modal_harvest_partial_batch_failure_reports_per_item_errors(self) -> None:
        capture_session_id = uuid4()
        good_item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        bad_item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000002",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, items=[good_item, bad_item])
        db = SimpleNamespace(commit=Mock())
        request = DouyinExtensionFullModalHarvestRequest(
            capture_session_id=capture_session_id,
            started_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="video_detail_page"),
            capture_context={"page_url": PROFILE_URL},
            items=[
                DouyinExtensionFullModalHarvestItemPayload(
                    aweme_id="7420000000000000001",
                    raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(like_count=5, extraction_source="dom_detail_modal", confidence="high"),
                    raw_detail_aweme=None,
                    raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                        has_dom_detail_metrics=True,
                        dom_detail_metric_keys=["like_count"],
                        evidence_sources=["full_modal_auto_harvest", "dom_detail_modal"],
                        evidence_collection_version="phase6h_full_modal_auto_harvest",
                    ),
                ),
                DouyinExtensionFullModalHarvestItemPayload(
                    aweme_id="7420000000000000002",
                    raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(like_count=6, extraction_source="dom_detail_modal", confidence="high"),
                    raw_detail_aweme=None,
                    raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                        has_dom_detail_metrics=True,
                        dom_detail_metric_keys=["like_count"],
                        evidence_sources=["full_modal_auto_harvest", "dom_detail_modal"],
                        evidence_collection_version="phase6h_full_modal_auto_harvest",
                    ),
                ),
            ],
            progress=DouyinExtensionFullModalHarvestProgress(
                running=False,
                target_count=49,
                current_aweme_id=None,
                harvested_count=2,
                updated_count=0,
                duplicate_count=0,
                failed_count=0,
                flushed_count=0,
                last_error=None,
                stopped_reason="operator_stopped",
            ),
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls, patch.object(
            DouyinExtensionCaptureService,
            "_apply_modal_harvest_to_item",
            side_effect=[{"updated": True, "duration_updated": False, "like_updated": True, "comment_updated": False, "favorite_updated": False, "share_updated": False}, RuntimeError("bad item")],
        ):
            inbox_cls.return_value.get_session.return_value = session
            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertEqual(result.updated_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.failure_summaries[0]["aweme_id"], "7420000000000000002")

    def test_full_modal_harvest_rejects_identity_mismatch_and_does_not_update_item(self) -> None:
        capture_session_id = uuid4()
        item = SimpleNamespace(
            id=uuid4(),
            source_video_external_id="7420000000000000001",
            metadata_json={},
            raw_payload_json={},
            posted_at=None,
            duration_seconds=None,
            preview_ready=True,
            status=CapturedItemStatus.NEEDS_ENRICHMENT,
        )
        session = SimpleNamespace(id=capture_session_id, items=[item])
        db = SimpleNamespace(commit=Mock())
        request = DouyinExtensionFullModalHarvestRequest(
            capture_session_id=capture_session_id,
            started_at=datetime.now(UTC),
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="video_detail_page"),
            capture_context={"page_url": PROFILE_URL},
            items=[
                DouyinExtensionFullModalHarvestItemPayload(
                    aweme_id="7420000000000000001",
                    target_aweme_id="7420000000000000001",
                    modal_aweme_id_before_extract="7420000000000000001",
                    modal_aweme_id_after_extract="7420000000000000999",
                    extracted_aweme_id="7420000000000000001",
                    data_integrity_status="mismatch",
                    data_integrity_reason="modal_aweme_changed_before_commit",
                    raw_dom_detail_metrics=DouyinExtensionRawDomDetailMetrics(like_count=5, extraction_source="dom_detail_modal", confidence="high"),
                    raw_detail_aweme=None,
                    raw_evidence_summary=DouyinExtensionRawEvidenceSummary(
                        has_dom_detail_metrics=True,
                        dom_detail_metric_keys=["like_count"],
                        evidence_sources=["full_modal_auto_harvest", "dom_detail_modal"],
                        evidence_collection_version="phase6h_full_modal_auto_harvest",
                    ),
                )
            ],
            progress=DouyinExtensionFullModalHarvestProgress(
                running=False,
                target_count=1,
                current_aweme_id="7420000000000000001",
                harvested_count=1,
                updated_count=0,
                duplicate_count=0,
                failed_count=1,
                flushed_count=1,
                last_error=None,
                stopped_reason="operator_stopped",
            ),
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.get_session.return_value = session
            result = DouyinExtensionCaptureService(db=db).ingest_full_modal_harvest(request)

        self.assertFalse(result.ok)
        self.assertFalse(result.success)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.idempotent_unchanged_count, 0)
        self.assertEqual(result.beta_write_effective_status, "failed")
        self.assertEqual(result.matched_count, 0)
        self.assertEqual(result.failure_summaries[0]["reason"], "data_integrity_mismatch")
        self.assertEqual(result.failure_summaries[0]["data_integrity_status"], "mismatch")
        inbox_cls.return_value._evaluate_items_against_intake.assert_not_called()
        db.commit.assert_not_called()

    def test_capture_current_page_preserves_unclassified_true_system_failures(self) -> None:
        request = DouyinExtensionCaptureRequest(
            capture_id="capture-system-failure-fixture",
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL, video_link_count=1),
            videos=[DouyinExtensionVideoPayload(aweme_id="7420000000000000001")],
            persist=True,
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            inbox_cls.return_value.stage_extension_capture.side_effect = RuntimeError("database unavailable")

            with self.assertRaises(RuntimeError):
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

    def test_capture_rejects_challenge_page_before_ingest(self) -> None:
        request = DouyinExtensionCaptureRequest(
            page=DouyinExtensionPageSnapshot(
                url="https://www.douyin.com/",
                title="Security check",
                body_text_sample="验证码",
                page_type="challenge_page",
            )
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

        self.assertEqual(ctx.exception.code, "extension_challenge_page_not_capturable")
        self.assertEqual(ctx.exception.stage, "classify_extension_page")
        inbox_cls.assert_not_called()

    def test_capture_rejects_secret_like_fields_before_ingest(self) -> None:
        request = DouyinExtensionCaptureRequest(
            page=DouyinExtensionPageSnapshot(url=PROFILE_URL, page_type="profile_page", profile_url=PROFILE_URL),
            diagnostics={"session_storage": "must-not-send"},
        )

        with patch("src.services.douyin_extension_capture_service.CaptureInboxService") as inbox_cls:
            with self.assertRaises(DouyinExtensionCaptureError) as ctx:
                DouyinExtensionCaptureService(db=SimpleNamespace()).capture_current_page(request, filter_config=None)

        self.assertEqual(ctx.exception.code, "extension_payload_contains_secret_field")
        self.assertEqual(ctx.exception.stage, "validate_extension_payload")
        inbox_cls.assert_not_called()

    def test_retry_enrich_re_evaluates_intake_for_selected_items(self) -> None:
        session_id = uuid4()
        item = SimpleNamespace(id=uuid4(), status=CapturedItemStatus.RAW, dedupe_key="dedupe-1")
        session = SimpleNamespace(id=session_id, items=[item])
        db = SimpleNamespace(commit=Mock())
        service = CaptureInboxService(db)

        with patch.object(service, "get_session", return_value=session), patch.object(
            service, "_selected_items", return_value=[item]
        ), patch.object(service, "_enrich_item") as enrich_mock, patch.object(
            service, "_evaluate_items_against_intake"
        ) as evaluate_mock, patch.object(service, "_reconcile_session") as reconcile_mock:
            result = service.retry_enrich(session_id, item_ids=[item.id])

        self.assertEqual(result, [item])
        enrich_mock.assert_called_once()
        evaluate_mock.assert_called_once_with([item], session=session)
        reconcile_mock.assert_called_once_with(session)
        db.commit.assert_called_once()

    def test_re_evaluate_intake_selected_items_runs_evaluator_and_commits(self) -> None:
        session_id = uuid4()
        item = SimpleNamespace(id=uuid4())
        session = SimpleNamespace(id=session_id, items=[item])
        db = SimpleNamespace(commit=Mock())
        service = CaptureInboxService(db)

        with patch.object(service, "get_session", return_value=session), patch.object(
            service, "_selected_items", return_value=[item]
        ), patch.object(service, "_evaluate_items_against_intake") as evaluate_mock, patch.object(
            service, "_reconcile_session"
        ) as reconcile_mock:
            result = service.re_evaluate_intake(session_id, item_ids=[item.id], preset_name="safe_reup")

        self.assertEqual(result, [item])
        evaluate_mock.assert_called_once_with([item], session=session, preset_name="safe_reup")
        reconcile_mock.assert_called_once_with(session)
        db.commit.assert_called_once()

    def test_capture_inbox_promotion_uses_canonical_ingest_and_candidate_evaluation(self) -> None:
        workspace_id = uuid4()
        session_id = uuid4()
        source_profile_id = uuid4()
        crawl_session_id = uuid4()
        source_video_id = uuid4()
        candidate_id = uuid4()
        item = CapturedItem(
            id=uuid4(),
            workspace_id=workspace_id,
            capture_session_id=session_id,
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.READY,
            raw_item_index=0,
            raw_payload_json={"statistics": {"like_count": 1200}},
            source_profile_external_id="MS4wLjABAAAAfixture-sec-uid",
            profile_url=PROFILE_URL,
            source_video_external_id="7420000000000000001",
            source_url="https://www.douyin.com/video/7420000000000000001",
            caption="Fixture video",
            thumbnail_url="https://cdn.example.test/thumb.jpg",
            metadata_json={
                "duration_text": "12s",
                "duration_source": "extension_card",
                "posted_text": "2026-05-10",
                "posted_display": "May 10, 2026",
                "posted_source": "extension_card",
                "estimated_views_text_raw": "1.2K views",
                "estimated_views_display": "1.2K",
                "estimated_views_min": 1100,
                "estimated_views_max": 1300,
                "estimated_views_mid": 1200,
                "estimated_views_parse_confidence": "high",
                "like_count": 1200,
                "like_count_text": "1.2K",
                "comment_count": 45,
                "comment_count_text": "45",
                "share_count": 12,
                "share_count_text": "12",
                "favorite_count": 8,
                "favorite_count_text": "8",
                "engagement_score": 0.42,
                "engagement_rate": 0.11,
                "engagement_rate_basis": "estimated_views_mid",
                "reup_score": 87,
                "reup_score_label": "High fit",
                "reup_score_level": "excellent",
                "reup_score_components": {"engagement": 42},
                "reup_score_reasons": ["Strong engagement"],
            },
            preview_ready=True,
            media_ready=False,
            readiness_reasons_json=[],
        )
        session = CaptureSession(
            id=session_id,
            workspace_id=workspace_id,
            capture_id="capture-fixture",
            source_platform=SourcePlatformEnum.DOUYIN,
            capture_source="douyin_extension_current_tab",
            status="READY_FOR_REVIEW",
            detected_page_type="profile_feed_page",
            page_url=PROFILE_URL,
            page_title="Fixture Creator",
            submitted_profile_url=PROFILE_URL,
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            visible_item_count=1,
            diagnostics_json={},
            metadata_json={},
            raw_summary_json={},
            result_summary_json={},
        )
        session.items = [item]
        ingest_summary = IngestSummary(
            crawl_session_id=str(crawl_session_id),
            status=CrawlSessionStatus.COMPLETED,
            source_profile_id=str(source_profile_id),
            source_platform=SourcePlatformEnum.DOUYIN,
            submitted_profile_url=PROFILE_URL,
            normalized_profile_identifier="MS4wLjABAAAAfixture-sec-uid",
            videos_discovered_count=1,
            videos_created_count=1,
            videos_updated_count=0,
            snapshots_created_count=1,
        )
        candidate_result = SimpleNamespace(total_count=1, matched_count=1, rejected_count=0, evaluations=[object()])
        db = SimpleNamespace(commit=lambda: None)
        service = CaptureInboxService(db)

        with patch.object(service, "get_session", return_value=session), patch.object(
            service, "_sync_existing_review_board_promotions", return_value=[]
        ), patch.object(
            service, "_candidate_ids_for_items", side_effect=[set(), {candidate_id}]
        ), patch.object(
            service, "_source_videos_by_external_id", return_value={"7420000000000000001": SimpleNamespace(id=source_video_id, metadata_json={})}
        ), patch.object(
            service, "_candidates_by_source_video_id", return_value={source_video_id: SimpleNamespace(id=candidate_id, source_video_id=source_video_id, metadata_json={})}
        ), patch("src.services.capture_inbox_service.SourceIngestService") as ingest_cls, patch(
            "src.services.capture_inbox_service.CandidateEvaluationService"
        ) as candidate_cls:
            ingest_cls.return_value.ingest_profile.return_value = ingest_summary
            candidate_cls.return_value.apply_for_source_videos.return_value = candidate_result

            result = service.promote(session_id, persist=True)

        ingest_call = ingest_cls.return_value.ingest_profile.call_args.kwargs
        self.assertEqual(ingest_call["workspace_id"], workspace_id)
        self.assertEqual(ingest_call["profile_url"], PROFILE_URL)
        self.assertEqual(ingest_call["source_platform"], SourcePlatformEnum.DOUYIN)
        self.assertEqual(ingest_call["crawl_mode"], CAPTURE_INBOX_CRAWL_MODE)
        self.assertEqual(ingest_call["adapter_payload_json"]["metadata"]["promotion_model"], "capture_inbox_to_canonical_review")
        promoted_video_payload = ingest_call["adapter_payload_json"]["videos"][0]
        self.assertEqual(promoted_video_payload["capture_item_id"], str(item.id))
        self.assertEqual(promoted_video_payload["capture_session_id"], str(session_id))
        self.assertEqual(promoted_video_payload["source"], "douyin")
        self.assertEqual(promoted_video_payload["source_module"], "capture_inbox")
        self.assertEqual(promoted_video_payload["source_video_external_id"], "7420000000000000001")
        self.assertEqual(promoted_video_payload["source_url"], "https://www.douyin.com/video/7420000000000000001")
        self.assertEqual(promoted_video_payload["profile_url"], PROFILE_URL)
        self.assertEqual(promoted_video_payload["video_url"], "https://www.douyin.com/video/7420000000000000001")
        self.assertEqual(promoted_video_payload["caption"], "Fixture video")
        self.assertEqual(promoted_video_payload["description"], "Fixture video")
        self.assertEqual(promoted_video_payload["thumbnail_url"], "https://cdn.example.test/thumb.jpg")
        self.assertEqual(promoted_video_payload["duration_text"], "12s")
        self.assertEqual(promoted_video_payload["duration_source"], "extension_card")
        self.assertEqual(promoted_video_payload["posted_text"], "2026-05-10")
        self.assertEqual(promoted_video_payload["posted_text_raw"], "2026-05-10")
        self.assertEqual(promoted_video_payload["posted_display"], "May 10, 2026")
        self.assertEqual(promoted_video_payload["posted_source"], "extension_card")
        self.assertEqual(promoted_video_payload["estimated_views_text_raw"], "1.2K views")
        self.assertEqual(promoted_video_payload["estimated_views_display"], "1.2K")
        self.assertEqual(promoted_video_payload["estimated_views_min"], 1100)
        self.assertEqual(promoted_video_payload["estimated_views_max"], 1300)
        self.assertEqual(promoted_video_payload["estimated_views_mid"], 1200)
        self.assertEqual(promoted_video_payload["estimated_views_parse_confidence"], "high")
        self.assertEqual(promoted_video_payload["like_count_text"], "1.2K")
        self.assertEqual(promoted_video_payload["comment_count_text"], "45")
        self.assertEqual(promoted_video_payload["share_count_text"], "12")
        self.assertEqual(promoted_video_payload["favorite_count"], 8)
        self.assertEqual(promoted_video_payload["favorite_count_text"], "8")
        self.assertEqual(promoted_video_payload["engagement_score"], 0.42)
        self.assertEqual(promoted_video_payload["engagement_rate_basis"], "estimated_views_mid")
        self.assertEqual(promoted_video_payload["reup_score"], 87)
        self.assertEqual(promoted_video_payload["reup_score_label"], "High fit")
        self.assertEqual(promoted_video_payload["reup_score_components"], {"engagement": 42})
        self.assertEqual(promoted_video_payload["reup_score_reasons"], ["Strong engagement"])
        self.assertEqual(promoted_video_payload["review_board_status"], "pending_review")
        self.assertEqual(promoted_video_payload["review_status"], "pending_review")
        self.assertEqual(promoted_video_payload["decision_status"], "pending_review")
        candidate_call = candidate_cls.return_value.apply_for_source_videos.call_args.kwargs
        self.assertTrue(candidate_call["shortlist_all"])
        self.assertTrue(candidate_call["persist"])
        self.assertEqual(result.promoted_item_count, 1)
        self.assertEqual(result.candidate_created_count, 1)
        self.assertEqual(result.skipped, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(item.status, CapturedItemStatus.PROMOTED)
        self.assertEqual(item.promoted_source_video_id, source_video_id)
        self.assertEqual(item.promoted_video_candidate_id, candidate_id)
        self.assertEqual(item.promoted_crawl_session_id, crawl_session_id)
        self.assertEqual(item.metadata_json["review_status"], "promoted")
        self.assertEqual(item.metadata_json["promoted_to_review_board_id"], str(candidate_id))
        self.assertTrue(item.metadata_json["review_board_handoff_verified"])
        self.assertFalse(item.metadata_json["review_board_duplicate_detected"])

    def test_capture_inbox_promotion_skips_missing_metadata_without_ingest(self) -> None:
        session_id = uuid4()
        item = CapturedItem(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_session_id=session_id,
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.READY,
            raw_item_index=0,
            raw_payload_json={},
            source_video_external_id="7420000000000000999",
            source_url="https://www.douyin.com/video/7420000000000000999",
            caption="Missing thumbnail fixture",
        )
        session = SimpleNamespace(id=session_id, items=[item], result_summary_json={})
        db = SimpleNamespace(commit=Mock())
        service = CaptureInboxService(db)

        with patch.object(service, "get_session", return_value=session), patch.object(service, "_reconcile_session") as reconcile_mock, patch(
            "src.services.capture_inbox_service.SourceIngestService"
        ) as ingest_cls:
            result = service.promote(session_id, item_ids=[item.id])

        self.assertEqual(result.promoted_item_count, 0)
        self.assertEqual([(skip.item_id, skip.reason) for skip in result.skipped], [(item.id, "missing_metadata")])
        ingest_cls.assert_not_called()
        reconcile_mock.assert_called_once_with(session)
        db.commit.assert_called_once()

    def test_capture_inbox_promotion_syncs_existing_review_board_duplicate(self) -> None:
        source_video_id = uuid4()
        candidate_id = uuid4()
        item = CapturedItem(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_session_id=uuid4(),
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.READY,
            raw_item_index=0,
            raw_payload_json={},
            source_video_external_id="7420000000000000001",
            source_url="https://www.douyin.com/video/7420000000000000001",
            caption="Duplicate fixture",
            thumbnail_url="https://cdn.example.test/thumb.jpg",
        )
        session = SimpleNamespace(id=uuid4(), submitted_profile_url="https://www.douyin.com/user/example")
        source_video = SimpleNamespace(id=source_video_id, metadata_json={}, raw_payload_json={}, source_url=item.source_url, caption="Stale fixture", posted_at=None, duration_seconds=None)
        candidate = SimpleNamespace(id=candidate_id, source_video_id=source_video_id, metadata_json={"reup_score": 21.1}, score=21.1)
        db = SimpleNamespace(get=Mock(return_value=None), scalar=Mock(side_effect=[source_video, candidate]), flush=Mock())
        service = CaptureInboxService(db)

        duplicates = service._sync_existing_review_board_promotions(session, [item])

        self.assertEqual(duplicates, [item])
        self.assertEqual(item.status, CapturedItemStatus.PROMOTED)
        self.assertEqual(item.promoted_source_video_id, source_video_id)
        self.assertEqual(item.promoted_video_candidate_id, candidate_id)
        self.assertEqual(item.metadata_json["review_board_item_id"], str(candidate_id))
        self.assertTrue(item.metadata_json["review_board_duplicate_detected"])
        self.assertEqual(candidate.metadata_json["capture_item_id"], str(item.id))
        self.assertEqual(candidate.metadata_json["source_video_external_id"], item.source_video_external_id)
        self.assertEqual(candidate.metadata_json["caption"], "Duplicate fixture")
        self.assertEqual(candidate.metadata_json["review_board_upsert_source"], "capture_inbox_duplicate_promote")

    def test_capture_inbox_service_list_sessions_recomputes_live_counts_from_items(self) -> None:
        ready_item = SimpleNamespace(status=CapturedItemStatus.READY, promoted_video_candidate_id=None)
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_id="capture-live-counts",
            source_platform=SourcePlatformEnum.DOUYIN,
            capture_source="whole_profile_harvest",
            status="RECEIVED",
            visible_item_count=1,
            captured_item_count=0,
            normalized_item_count=0,
            duplicate_item_count=0,
            ready_item_count=0,
            skipped_item_count=0,
            promoted_item_count=0,
            candidate_created_count=0,
            failed_item_count=0,
            started_at=None,
            finished_at=None,
            diagnostics_json=None,
            metadata_json={},
            raw_summary_json={},
            result_summary_json={},
            error_code=None,
            error_message=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            items=[ready_item],
        )
        db = SimpleNamespace(scalars=lambda _stmt: [session], scalar=lambda _stmt: 1)

        sessions, total = CaptureInboxService(db=db).list_sessions()

        self.assertEqual(total, 1)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(session.captured_item_count, 1)
        self.assertEqual(session.ready_item_count, 1)
        self.assertEqual(session.failed_item_count, 0)

    def test_capture_inbox_service_get_session_recomputes_live_counts_from_items(self) -> None:
        ready_item = SimpleNamespace(status=CapturedItemStatus.READY, promoted_video_candidate_id=None)
        session = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_id="capture-live-detail",
            source_platform=SourcePlatformEnum.DOUYIN,
            capture_source="whole_profile_harvest",
            status="RECEIVED",
            visible_item_count=1,
            captured_item_count=0,
            normalized_item_count=0,
            duplicate_item_count=0,
            ready_item_count=0,
            skipped_item_count=0,
            promoted_item_count=0,
            candidate_created_count=0,
            failed_item_count=0,
            started_at=None,
            finished_at=None,
            diagnostics_json=None,
            metadata_json={},
            raw_summary_json={},
            result_summary_json={},
            error_code=None,
            error_message=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            items=[ready_item],
        )
        db = SimpleNamespace(scalar=lambda _stmt: session)

        loaded = CaptureInboxService(db=db).get_session(session.id)

        self.assertIs(loaded, session)
        self.assertEqual(loaded.captured_item_count, 1)
        self.assertEqual(loaded.ready_item_count, 1)


if __name__ == "__main__":
    unittest.main()
