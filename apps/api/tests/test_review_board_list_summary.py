import inspect
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.enums import CandidateStatus
from src.schemas.candidates import CandidateListResponse, CandidateSummaryResponse
from src.services import candidate_service


class ReviewBoardListSummaryTests(unittest.TestCase):
    def _candidate(self, *, metadata=None, score=55.0):
        source = SimpleNamespace(
            id=uuid4(),
            source_profile_id=uuid4(),
            source_video_external_id="7420000000000000001",
            source_url="https://www.douyin.com/video/7420000000000000001",
            caption="Fixture caption",
            posted_at=datetime(2026, 1, 1, tzinfo=UTC),
            duration_seconds=61.0,
            metadata_json={"reup_score": 66, "estimated_views_display": "6.6K-8.8K"},
        )
        return SimpleNamespace(
            id=uuid4(),
            source_video_id=source.id,
            status=CandidateStatus.SHORTLISTED,
            score=score,
            score_version="REUP_SCORE_V1",
            score_label="usable",
            score_breakdown_json={},
            score_reason=None,
            preset_name="viral_discovery",
            filter_config_json={},
            inclusion_reasons_json=[],
            exclusion_reasons_json=[],
            warnings_json=[],
            evaluated_at=None,
            priority=55,
            metadata_json=metadata or {"reup_score": 66, "estimated_views_display": "6.6K-8.8K", "duration_text": "01:01"},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_video=source,
        )

    def test_list_candidates_defaults_hydrate_false_for_summary_path(self) -> None:
        source = inspect.getsource(candidate_service.CandidateEvaluationService.list_candidates)
        self.assertIn("hydrate_from_capture_inbox", source)

        route_source = inspect.getsource(__import__("src.api.routes.candidates", fromlist=["list_candidates"]).list_candidates)
        self.assertIn('view', route_source)
        self.assertIn("CandidateSummaryResponse", route_source)

    def test_candidate_summary_response_is_lightweight(self) -> None:
        candidate = self._candidate()
        summary = CandidateSummaryResponse.from_candidate(candidate)

        self.assertEqual(summary.caption, "Fixture caption")
        self.assertEqual(summary.reup_score, 66)
        self.assertEqual(summary.estimated_views_display, "6.6K-8.8K")
        self.assertEqual(summary.duration_text, "01:01")
        dumped = summary.model_dump()
        self.assertIn("like_count", dumped)
        self.assertIn("engagement_rate", dumped)
        self.assertIn("estimated_views_mid", dumped)
        self.assertNotIn("score_breakdown_json", dumped)
        self.assertNotIn("review_candidate_debug", dumped)
        self.assertLess(len(dumped.keys()), 35)

    def test_candidate_list_response_supports_summary_view_contract(self) -> None:
        candidate = self._candidate()
        summary = CandidateSummaryResponse.from_candidate(candidate)
        payload = CandidateListResponse(
            view="summary",
            total_count=1,
            offset=0,
            limit=50,
            candidates=[summary],
        )

        self.assertEqual(payload.view, "summary")
        self.assertEqual(payload.total_count, 1)
        self.assertEqual(payload.candidates[0].caption, "Fixture caption")


if __name__ == "__main__":
    unittest.main()
