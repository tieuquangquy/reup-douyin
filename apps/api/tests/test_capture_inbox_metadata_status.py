from datetime import UTC, datetime
import unittest
from uuid import uuid4

from src.enums import CapturedItemStatus, IntakeEvaluationStatus, SourcePlatformEnum
from src.schemas.capture_inbox import CapturedItemResponse, CaptureSessionResponse
from src.enums import CaptureSessionStatus


def _item_response(**overrides):
    now = datetime.now(UTC)
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "capture_session_id": uuid4(),
        "source_platform": SourcePlatformEnum.DOUYIN,
        "status": CapturedItemStatus.RAW,
        "raw_item_index": 0,
        "source_video_external_id": "7420000000000000001",
        "source_url": "https://www.douyin.com/video/7420000000000000001",
        "preview_ready": False,
        "media_ready": False,
        "metadata_json": {},
        "raw_payload_json": {},
        "intake_evaluation_status": IntakeEvaluationStatus.NOT_EVALUATED,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return CapturedItemResponse.model_validate(payload)


class CaptureInboxMetadataStatusTests(unittest.TestCase):
    def test_metadata_status_complete_item(self) -> None:
        item = _item_response(
            thumbnail_url="https://p3.douyinpic.com/obj/complete-thumbnail",
            metadata_json={
                "posted_at": "2026-04-29T10:00:00+00:00",
                "duration_seconds": 12,
                "view_count": 100,
                "like_count": 20,
                "comment_count": 0,
                "share_count": 0,
                "posted_source": "network_json",
                "duration_source": "network_json",
                "view_count_source": "network_json",
                "comment_count_source": "dom_zero_sentinel",
                "share_count_source": "dom_zero_sentinel",
                "last_metadata_hydrated_at": "2026-04-29T10:01:00+00:00",
            }
        )

        self.assertEqual(item.metadata_status, "complete")
        self.assertTrue(item.has_all_core_metadata)
        self.assertEqual(item.time_status, "captured")
        self.assertEqual(item.performance_status, "captured")
        self.assertEqual(item.processing_fit_status, "captured")
        self.assertIsNone(item.metadata_missing_reason)
        self.assertIsNotNone(item.last_metadata_hydrated_at)

    def test_metadata_status_partial_when_core_engagement_missing(self) -> None:
        item = _item_response(
            thumbnail_url="https://p3.douyinpic.com/obj/complete-thumbnail",
            metadata_json={
                "posted_at": "2026-04-29T10:00:00+00:00",
                "duration_seconds": 12,
                "view_count": 100,
                "like_count": 20,
                "posted_source": "network_json",
                "duration_source": "network_json",
                "view_count_source": "network_json",
                "last_metadata_hydrated_at": "2026-04-29T10:01:00+00:00",
            }
        )

        self.assertEqual(item.metadata_status, "partial")
        self.assertFalse(item.has_all_core_metadata)
        self.assertIn("comments", item.missing_metadata_fields)
        self.assertIn("shares", item.missing_metadata_fields)

    def test_metadata_status_hydrates_zero_comment_sentinel_from_text(self) -> None:
        item = _item_response(
            thumbnail_url="https://p3.douyinpic.com/obj/thumb",
            metadata_json={
                "duration_seconds": 12,
                "posted_at": "2026-04-29T10:00:00+00:00",
                "view_count": 100,
                "like_count": 20,
                "comment_count_text": "抢首评",
                "share_count_text": "分享",
                "comment_count_source": "dom_zero_sentinel",
                "share_count_source": "dom_zero_sentinel",
                "schema_version": "fixture",
            },
        )

        self.assertEqual(item.comment_count, 0)
        self.assertEqual(item.share_count, 0)
        self.assertTrue(item.has_comments)
        self.assertTrue(item.has_shares)

    def test_metadata_status_partial_item(self) -> None:
        item = _item_response(
            metadata_json={"posted_text": "昨天", "posted_source": "dom_snapshot", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.metadata_status, "partial")
        self.assertEqual(item.time_status, "captured")
        self.assertEqual(item.performance_status, "missing")
        self.assertEqual(item.processing_fit_status, "missing")
        self.assertEqual(item.performance_missing_reason, "No view_count or like_count captured.")
        self.assertEqual(item.posted_text, "08/05/2026")
        self.assertEqual(item.posted_text_raw, "昨天")
        self.assertEqual(item.posted_display, "08/05/2026")

    def test_metadata_status_missing_item(self) -> None:
        item = _item_response(metadata_json={"schema_version": "fixture", "posted_source": "fallback_none"})

        self.assertEqual(item.metadata_status, "missing")
        self.assertEqual(item.time_status, "missing")
        self.assertEqual(item.performance_status, "missing")
        self.assertEqual(item.processing_fit_status, "missing")
        self.assertIsNotNone(item.metadata_missing_reason)

    def test_metadata_status_pending_item(self) -> None:
        item = _item_response(metadata_json={}, raw_payload_json={})

        self.assertEqual(item.metadata_status, "pending_hydration")
        self.assertEqual(item.time_status, "pending")
        self.assertEqual(item.performance_status, "pending")
        self.assertEqual(item.processing_fit_status, "pending")
        self.assertEqual(item.metadata_missing_reason, "Metadata hydration has not been attempted.")

    def test_metadata_status_failed_item(self) -> None:
        item = _item_response(status=CapturedItemStatus.FAILED, error_code="metadata_hydration_failed", error_message="fixture failure")

        self.assertEqual(item.metadata_status, "failed")
        self.assertEqual(item.time_status, "failed")
        self.assertEqual(item.performance_status, "failed")
        self.assertEqual(item.processing_fit_status, "failed")
        self.assertEqual(item.metadata_missing_reason, "Metadata hydration failed.")

    def test_metadata_status_api_serializes_status_fields(self) -> None:
        item = _item_response(metadata_json={"duration_seconds": 8, "view_count": 10, "schema_version": "fixture"})
        dumped = item.model_dump(mode="json")

        self.assertEqual(dumped["metadata_status"], "partial")
        self.assertEqual(dumped["time_status"], "missing")
        self.assertEqual(dumped["performance_status"], "captured")
        self.assertEqual(dumped["processing_fit_status"], "captured")
        self.assertIn("metadata_missing_reason", dumped)
        self.assertIn("metadata_source_summary", dumped)
        self.assertIn("last_metadata_hydrated_at", dumped)

    def test_response_keeps_posted_text_without_posted_at(self) -> None:
        item = _item_response(
            metadata_json={"posted_text": "12小时前", "posted_source": "modal_author_row", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.posted_text, "09/05/2026")
        self.assertEqual(item.posted_text_raw, "12小时前")
        self.assertEqual(item.posted_display, "09/05/2026")
        self.assertEqual(item.posted_source, "modal_author_row")
        self.assertEqual(item.time_status, "captured")

    def test_response_lazy_normalizes_relative_day_offsets_to_dd_mm_yyyy(self) -> None:
        item = _item_response(
            metadata_json={"posted_text": "4天前", "posted_source": "profile_card", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.posted_text, "05/05/2026")
        self.assertEqual(item.posted_text_raw, "4天前")
        self.assertEqual(item.posted_display, "05/05/2026")
        self.assertIsNotNone(item.posted_at)

    def test_response_lazy_normalizes_relative_week_offsets_to_dd_mm_yyyy(self) -> None:
        item = _item_response(
            metadata_json={"posted_text": "1周前", "posted_source": "profile_card", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.posted_text, "02/05/2026")
        self.assertEqual(item.posted_text_raw, "1周前")
        self.assertEqual(item.posted_display, "02/05/2026")
        self.assertIsNotNone(item.posted_at)

    def test_response_lazy_normalizes_relative_week_chinese_numeral_offsets(self) -> None:
        item = _item_response(
            metadata_json={"posted_text": "两星期前", "posted_source": "profile_card", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.posted_text, "25/04/2026")
        self.assertEqual(item.posted_text_raw, "两星期前")
        self.assertEqual(item.posted_display, "25/04/2026")
        self.assertIsNotNone(item.posted_at)

    def test_response_lazy_normalizes_chinese_month_day_without_year(self) -> None:
        item = _item_response(
            metadata_json={"posted_text_raw": "@地球之旅 · 4月28日", "posted_source": "modal_author_row", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.posted_text, "28/04/2026")
        self.assertEqual(item.posted_text_raw, "@地球之旅 · 4月28日")
        self.assertEqual(item.posted_display, "28/04/2026")
        self.assertIsNotNone(item.posted_at)

    def test_response_lazy_normalizes_future_month_day_to_previous_year(self) -> None:
        item = _item_response(
            metadata_json={"posted_text": "12月31日", "posted_source": "profile_card", "schema_version": "fixture"},
            updated_at=datetime(2026, 1, 5, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(item.posted_text, "31/12/2025")
        self.assertEqual(item.posted_display, "31/12/2025")
        self.assertIsNotNone(item.posted_at)

    def test_response_lazy_normalizes_absolute_and_english_posted_text(self) -> None:
        absolute = _item_response(
            metadata_json={"posted_text": "2026年4月28日", "posted_source": "profile_card", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )
        english = _item_response(
            metadata_json={"posted_text": "Apr 28", "posted_source": "profile_card", "schema_version": "fixture"},
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(absolute.posted_display, "28/04/2026")
        self.assertEqual(english.posted_display, "28/04/2026")

    def test_response_preserves_unparseable_posted_text_without_faking_date(self) -> None:
        item = _item_response(metadata_json={"posted_text": "很久以前", "posted_source": "profile_card", "schema_version": "fixture"})

        self.assertEqual(item.posted_text, "很久以前")
        self.assertEqual(item.posted_text_raw, "很久以前")
        self.assertIsNone(item.posted_display)
        self.assertIsNone(item.posted_at)

    def test_response_exposes_phase22d_normalized_duration_views_engagement_and_quality_fields(self) -> None:
        item = _item_response(
            thumbnail_url="https://p3.douyinpic.com/obj/thumb",
            metadata_json={
                "duration_text": "10:47",
                "posted_text": "2026年4月28日",
                "posted_source": "modal_author_row_profile_link",
                "estimated_views_display": "9K–43K",
                "like_count_text": "1.2K",
                "comment_count_text": "34",
                "share_count_text": "5",
                "favorite_count_text": "6",
                "schema_version": "fixture",
            },
            updated_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        )
        dumped = item.model_dump(mode="json")

        self.assertEqual(item.duration_text_raw, "10:47")
        self.assertEqual(item.duration_text, "10:47")
        self.assertEqual(item.duration_seconds, 647)
        self.assertEqual(item.duration_parse_confidence, "high")
        self.assertEqual(item.posted_text_raw, "2026年4月28日")
        self.assertEqual(item.posted_text, "28/04/2026")
        self.assertEqual(item.posted_display, "28/04/2026")
        self.assertEqual(item.posted_source, "modal_author_row_profile_link")
        self.assertEqual(item.posted_parse_confidence, "high")
        self.assertEqual(item.estimated_views_text_raw, "9K–43K")
        self.assertEqual(item.estimated_views_display, "9K–43K")
        self.assertEqual((item.estimated_views_min, item.estimated_views_max, item.estimated_views_mid), (9000, 43000, 26000))
        self.assertEqual(item.like_count, 1200)
        self.assertEqual(item.comment_count, 34)
        self.assertEqual(item.share_count, 5)
        self.assertEqual(item.favorite_count, 6)
        self.assertEqual(item.engagement_score, 1245)
        self.assertEqual(item.engagement_rate, 0.047885)
        self.assertEqual(item.engagement_rate_basis, "estimated_views_mid")
        self.assertTrue(item.has_all_core_metadata)
        self.assertEqual(item.missing_metadata_fields, [])
        self.assertIn("estimated_views_display", dumped)
        self.assertIn("has_all_core_metadata", dumped)

    def test_response_lazily_normalizes_legacy_exact_view_count_without_mutating_raw_fields(self) -> None:
        item = _item_response(
            metadata_json={
                "duration_seconds": 0,
                "duration_text": "00:00",
                "posted_text": "很久以前",
                "view_count_text": "432K",
                "like_count": 20,
                "comment_count": 3,
                "share_count": 1,
                "schema_version": "fixture",
            }
        )

        self.assertEqual(item.duration_text_raw, "00:00")
        self.assertEqual(item.duration_text, "00:00")
        self.assertEqual(item.estimated_views_display, "432K")
        self.assertEqual(item.estimated_views_mid, 432000)
        self.assertEqual(item.engagement_score, 24)
        self.assertEqual(item.engagement_rate_basis, "estimated_views_mid")
        self.assertEqual(item.posted_text, "很久以前")
        self.assertEqual(item.posted_text_raw, "很久以前")
        self.assertFalse(item.has_all_core_metadata)
        self.assertIn("thumbnail", item.missing_metadata_fields)

    def test_session_response_derives_alias_counts_and_needs_action(self) -> None:
        session = CaptureSessionResponse.model_validate(
            {
                "id": uuid4(),
                "workspace_id": uuid4(),
                "capture_id": "capture-session-fixture",
                "source_platform": SourcePlatformEnum.DOUYIN,
                "capture_source": "whole_profile_harvest",
                "status": CaptureSessionStatus.READY_FOR_REVIEW,
                "visible_item_count": 1,
                "captured_item_count": 1,
                "normalized_item_count": 1,
                "duplicate_item_count": 0,
                "ready_item_count": 1,
                "skipped_item_count": 0,
                "promoted_item_count": 0,
                "candidate_created_count": 0,
                "failed_item_count": 0,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )

        self.assertEqual(session.captured_count, 1)
        self.assertEqual(session.ready_count, 1)
        self.assertEqual(session.duplicate_count, 0)
        self.assertEqual(session.failed_count, 0)
        self.assertEqual(session.needs_action_count, 0)


if __name__ == "__main__":
    unittest.main()
