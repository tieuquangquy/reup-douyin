from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest

from src.enums import CapturedItemStatus
from src.services.capture_inbox_service import (
    _canonical_reup_score_for_capture_item,
    _resolve_follower_count_for_capture_item,
)


def _item(**overrides):
    base = {
        "status": CapturedItemStatus.READY,
        "thumbnail_url": "https://cdn.example/thumb.jpg",
        "duration_seconds": 42.0,
        "posted_at": datetime.now(UTC) - timedelta(hours=12),
        "metadata_json": {},
        "raw_payload_json": {},
        "duplicate_of_item_id": None,
        "existing_source_video_id": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class CaptureInboxReupScoreTests(unittest.TestCase):
    def test_performance_sweet_spot(self) -> None:
        item = _item()
        estimated_views = {"estimated_views_mid": 500_000}
        score = _canonical_reup_score_for_capture_item(item, metadata={}, raw={}, stats={}, estimated_views=estimated_views)
        self.assertEqual(score["reup_score_components"]["performance"], 20)

    def test_engagement_uses_likes_and_comments_only(self) -> None:
        item = _item()
        metadata = {"like_count": 16_000, "comment_count": 4_000, "share_count": 50_000}
        estimated_views = {"estimated_views_mid": 200_000}
        score = _canonical_reup_score_for_capture_item(item, metadata=metadata, raw={}, stats={}, estimated_views=estimated_views)
        self.assertEqual(score["reup_score_components"]["engagement"], 20)

    def test_low_view_engagement_cap(self) -> None:
        item = _item()
        metadata = {"like_count": 400, "comment_count": 100}
        estimated_views = {"estimated_views_mid": 5_000}
        score = _canonical_reup_score_for_capture_item(item, metadata=metadata, raw={}, stats={}, estimated_views=estimated_views)
        self.assertEqual(score["reup_score_components"]["engagement"], 10)

    def test_virality_retention_with_favorites(self) -> None:
        item = _item()
        metadata = {"share_count": 2_000, "favorite_count": 500, "like_count": 1_000, "comment_count": 100}
        estimated_views = {"estimated_views_mid": 100_000}
        score = _canonical_reup_score_for_capture_item(item, metadata=metadata, raw={}, stats={}, estimated_views=estimated_views)
        self.assertEqual(score["reup_score_components"]["virality_retention"], 20)

    def test_outlier_bonus(self) -> None:
        item = _item()
        metadata = {"follower_count": 10_000, "like_count": 1_000, "comment_count": 100, "share_count": 500, "favorite_count": 200}
        estimated_views = {"estimated_views_mid": 500_000}
        score = _canonical_reup_score_for_capture_item(item, metadata=metadata, raw={}, stats={}, estimated_views=estimated_views)
        self.assertEqual(score["reup_score_components"]["outlier_bonus"], 15)
        self.assertLessEqual(score["reup_score"], 100)

    def test_resolve_follower_count_from_session_context(self) -> None:
        follower = _resolve_follower_count_for_capture_item(
            metadata={},
            raw={},
            session_metadata={"capture_context": {"follower_count": 12_345}},
        )
        self.assertEqual(follower, 12_345)

    def test_ignores_stale_persisted_reup_score(self) -> None:
        item = _item()
        metadata = {
            "reup_score": 88,
            "reup_score_label": "Excellent",
            "reup_score_level": "excellent",
            "like_count": 16_000,
            "comment_count": 4_000,
        }
        estimated_views = {"estimated_views_mid": 200_000}
        score = _canonical_reup_score_for_capture_item(item, metadata=metadata, raw={}, stats={}, estimated_views=estimated_views)
        self.assertNotEqual(score["reup_score"], 88)
        self.assertEqual(score["reup_score_components"]["engagement"], 20)


if __name__ == "__main__":
    unittest.main()
