"""Capture Inbox promote must upsert a candidate for every promoted source video."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import CandidateStatus
from src.services.candidate_filter import apply_candidate_filter
from src.services.candidate_service import CandidateEvaluationService
from src.services.candidate_types import (
    CandidateSourceRecord,
    ContentSignals,
    FilterConfig,
    FilterSortOption,
    MetricSnapshotInput,
)


def _record(key: str) -> CandidateSourceRecord:
    return CandidateSourceRecord(
        source_video_id=key,
        source_profile_id=uuid4(),
        source_video_external_id=key,
        source_url=f"https://www.douyin.com/video/{key}",
        caption=f"video {key}",
        posted_at=datetime(2026, 5, 1, tzinfo=UTC),
        duration_seconds=30.0,
        metrics=MetricSnapshotInput(view_count=10_000, like_count=500, comment_count=20, share_count=10),
        content_signals=ContentSignals(),
        metadata_json={},
    )


class CaptureInboxPromoteCandidateLimitTests(unittest.TestCase):
    def test_default_filter_config_caps_profile_apply_at_fifty(self) -> None:
        records = [_record(f"vid-{index:03d}") for index in range(64)]
        result = apply_candidate_filter(records, FilterConfig(sort=FilterSortOption.SCORE_DESC))
        self.assertEqual(result.total_count, 64)
        self.assertEqual(len(result.evaluations), 50)

    def test_apply_for_source_videos_shortlists_every_requested_video(self) -> None:
        source_video_ids = [uuid4() for _ in range(64)]
        records = [
            CandidateSourceRecord(
                source_video_id=source_video_ids[index],
                source_profile_id=uuid4(),
                source_video_external_id=f"vid-{index:03d}",
                source_url=f"https://www.douyin.com/video/vid-{index:03d}",
                caption=f"video {index}",
                posted_at=datetime(2026, 5, 1, tzinfo=UTC),
                duration_seconds=30.0,
                metrics=MetricSnapshotInput(view_count=10_000, like_count=500, comment_count=20, share_count=10),
                content_signals=ContentSignals(),
                metadata_json={},
            )
            for index in range(64)
        ]
        db = MagicMock()
        service = CandidateEvaluationService(db)
        with patch.object(service, "_load_records_for_videos", return_value=records), patch.object(
            service, "_upsert_candidate", side_effect=lambda evaluation, *_args, **_kwargs: SimpleNamespace(
                id=uuid4(),
                source_video_id=evaluation.record.source_video_id,
                status=CandidateStatus.SHORTLISTED,
            )
        ) as upsert:
            result = service.apply_for_source_videos(
                source_video_ids=source_video_ids,
                persist=True,
                shortlist_all=True,
            )

        self.assertEqual(result.total_count, 64)
        self.assertEqual(result.matched_count, 64)
        self.assertEqual(len(result.evaluations), 64)
        self.assertEqual(upsert.call_count, 64)
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
