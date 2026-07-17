from __future__ import annotations

from datetime import UTC, datetime
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from src.enums import CapturedItemStatus, IntakeEvaluationStatus, SourcePlatformEnum
from src.models.capture_inbox import CapturedItem
from src.schemas.capture_inbox import CapturedItemResponse
from src.services.capture_inbox_engagement_backfill_service import (
    CaptureInboxEngagementBackfillService,
    apply_engagement_backfill_to_item,
    build_engagement_backfill_plan,
    item_needs_engagement_backfill,
    merge_hydrated_engagement_metadata,
)


class CaptureInboxEngagementBackfillServiceTests(unittest.TestCase):
    def test_build_plan_recovers_zero_comment_sentinel_from_stored_text(self) -> None:
        metadata = {
            "like_count": 20,
            "view_count": 100,
            "comment_count_text": "抢首评",
            "share_count_text": "分享",
            "duration_seconds": 12,
            "posted_at": "2026-04-29T10:00:00+00:00",
            "thumbnail_url": "https://cdn.example.test/thumb.jpg",
        }
        plan = build_engagement_backfill_plan(
            metadata=metadata,
            raw_payload={},
            existing_comment_count=None,
            existing_share_count=None,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.comment_count, 0)
        self.assertEqual(plan.comment_count_source, "dom_zero_sentinel")
        self.assertEqual(plan.share_count, 0)
        self.assertEqual(plan.share_count_source, "dom_zero_sentinel")

    def test_build_plan_recovers_api_zero_statistics_without_sentinel_text(self) -> None:
        metadata = {
            "raw_network_aweme": {
                "aweme_id": "7420000000000000001",
                "statistics": {"comment_count": 0, "share_count": 0, "digg_count": 5},
            }
        }
        plan = build_engagement_backfill_plan(
            metadata=metadata,
            raw_payload={},
            existing_comment_count=None,
            existing_share_count=None,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.comment_count, 0)
        self.assertEqual(plan.share_count, 0)
        self.assertEqual(plan.comment_count_source, "network_json")
        self.assertEqual(plan.share_count_source, "network_json")

    def test_build_plan_returns_none_when_no_recoverable_evidence(self) -> None:
        plan = build_engagement_backfill_plan(
            metadata={"like_count": 10},
            raw_payload={},
            existing_comment_count=None,
            existing_share_count=None,
        )
        self.assertIsNone(plan)

    def test_build_plan_does_not_override_existing_non_null_counts(self) -> None:
        metadata = {"comment_count_text": "抢首评", "share_count_text": "分享"}
        plan = build_engagement_backfill_plan(
            metadata=metadata,
            raw_payload={},
            existing_comment_count=12,
            existing_share_count=None,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertIsNone(plan.comment_count)
        self.assertEqual(plan.share_count, 0)

    def test_apply_backfill_updates_metadata_and_hydrated_quality_flags(self) -> None:
        now = datetime.now(UTC)
        item = CapturedItem(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_session_id=uuid4(),
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.READY,
            raw_item_index=0,
            raw_payload_json={},
            source_video_external_id="7420000000000000001",
            thumbnail_url="https://cdn.example.test/thumb.jpg",
            duration_seconds=12,
            posted_at=now,
            intake_evaluation_status=IntakeEvaluationStatus.NOT_EVALUATED,
            created_at=now,
            updated_at=now,
            metadata_json={
                "duration_seconds": 12,
                "posted_at": now.isoformat(),
                "view_count": 100,
                "like_count": 20,
                "comment_count_text": "抢首评",
                "share_count_text": "分享",
                "thumbnail_url": "https://cdn.example.test/thumb.jpg",
            },
            preview_ready=True,
            media_ready=False,
        )

        result = apply_engagement_backfill_to_item(item)

        self.assertEqual(result.outcome, "updated")
        self.assertTrue(result.comment_recovered)
        self.assertTrue(result.share_recovered)
        self.assertEqual(item.metadata_json["comment_count"], 0)
        self.assertEqual(item.metadata_json["share_count"], 0)
        self.assertEqual(item.metadata_json["comment_count_source"], "dom_zero_sentinel")
        self.assertEqual(item.metadata_json["share_count_source"], "dom_zero_sentinel")

        response = CapturedItemResponse.model_validate(item)
        self.assertEqual(response.comment_count, 0)
        self.assertEqual(response.share_count, 0)
        self.assertTrue(response.has_all_core_metadata)

    def test_merge_hydrated_engagement_metadata_preserves_backfill_audit_fields(self) -> None:
        metadata = {
            "comment_count": 0,
            "engagement_zero_backfill_at": "2026-07-13T00:00:00+00:00",
            "engagement_zero_backfill_source": "stored_evidence_replay",
        }
        response = CapturedItemResponse.model_validate(
            {
                "id": uuid4(),
                "workspace_id": uuid4(),
                "capture_session_id": uuid4(),
                "source_platform": SourcePlatformEnum.DOUYIN,
                "status": CapturedItemStatus.READY,
                "raw_item_index": 0,
                "metadata_json": metadata,
                "raw_payload_json": metadata,
                "preview_ready": False,
                "media_ready": False,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        merged = merge_hydrated_engagement_metadata(metadata, response)
        self.assertEqual(merged["engagement_zero_backfill_source"], "stored_evidence_replay")
        self.assertIn("has_all_core_metadata", merged)

    def test_item_needs_engagement_backfill_when_either_metric_missing(self) -> None:
        item = CapturedItem(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_session_id=uuid4(),
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.READY,
            raw_item_index=0,
            raw_payload_json={},
            metadata_json={"comment_count": 0, "share_count": None},
            preview_ready=False,
            media_ready=False,
        )
        self.assertTrue(item_needs_engagement_backfill(item))

    def test_service_skips_items_without_recoverable_evidence(self) -> None:
        item = CapturedItem(
            id=uuid4(),
            workspace_id=uuid4(),
            capture_session_id=uuid4(),
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.READY,
            raw_item_index=0,
            raw_payload_json={},
            metadata_json={"like_count": 10, "comment_count": None, "share_count": None},
            preview_ready=False,
            media_ready=False,
        )
        db = MagicMock()
        service = CaptureInboxEngagementBackfillService(db)
        results = service.backfill_items([item], dry_run=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].outcome, "no_recoverable_evidence")


if __name__ == "__main__":
    unittest.main()
