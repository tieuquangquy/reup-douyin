from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_AUTH_REQUIRED", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-thirty-two-characters")

from src.api.routes.capture_inbox import _safe_profile_item_response
from src.enums import CapturedItemStatus


class SafeProfileItemEngagementTests(unittest.TestCase):
    def test_safe_profile_item_response_hydrates_zero_counts_from_dom_sentinel_text(self) -> None:
        now = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
        item = SimpleNamespace(
            id=uuid4(),
            capture_session_id=uuid4(),
            status=CapturedItemStatus.READY,
            source_profile_external_id="profile",
            profile_url="https://www.douyin.com/user/profile",
            source_video_external_id="7633842656648416518",
            metadata_json={
                "metadata_status": "complete",
                "like_count": 24,
                "raw_dom_detail_metrics": {
                    "comment_count_text": "抢首评",
                    "share_count_text": "分享",
                },
            },
            raw_payload_json={},
            created_at=now,
            updated_at=now,
        )

        response = _safe_profile_item_response(item, normalized_profile_url="https://www.douyin.com/user/profile")

        self.assertEqual(response.comment_count, 0)
        self.assertEqual(response.share_count, 0)


if __name__ == "__main__":
    unittest.main()
