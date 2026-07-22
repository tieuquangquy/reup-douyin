import inspect
import unittest

from src.enums import CandidateStatus


class ReviewBoardCandidateSearchTests(unittest.TestCase):
    def test_list_candidates_route_accepts_search_query(self) -> None:
        from src.api.routes import candidates as candidate_routes

        route_source = inspect.getsource(candidate_routes.list_candidates)
        self.assertIn("search", route_source)
        self.assertIn("search=search", route_source)

    def test_candidate_service_applies_search_filter(self) -> None:
        from src.services import candidate_service

        list_source = inspect.getsource(candidate_service.CandidateEvaluationService.list_candidates)
        count_source = inspect.getsource(candidate_service.CandidateEvaluationService.count_candidates)
        filter_source = inspect.getsource(candidate_service.CandidateEvaluationService._apply_candidate_list_filters)
        self.assertIn("search", list_source)
        self.assertIn("search", count_source)
        self.assertIn("source_video_external_id", filter_source)
        self.assertIn("metadata_json", filter_source)
        self.assertIn("cast(VideoCandidate.metadata_json, Text)", filter_source)
        self.assertNotIn("coalesce(VideoCandidate.metadata_json, {})", filter_source)
        self.assertIn("VideoCandidate.id.asc()", list_source, "Offset pagination needs a stable unique tie-breaker")

    def test_candidate_list_returns_database_status_counts(self) -> None:
        from src.api.routes.candidates import list_candidates

        class FakeCandidateService:
            def count_candidates(self, **kwargs):
                return 378

            def count_candidates_by_status(self, **kwargs):
                return {
                    "NEW": 0,
                    "SHORTLISTED": 925,
                    "IN_REVIEW": 0,
                    "APPROVED": 84,
                    "REJECTED": 0,
                }

            def list_candidates(self, **kwargs):
                return []

        class FakeQueueService:
            def membership_for_candidates(self, candidate_ids):
                return {}

        response = list_candidates(
            status_filter=None,
            min_score=None,
            max_score=None,
            source_profile_id=None,
            search=None,
            limit=200,
            offset=0,
            view="summary",
            hydrate=False,
            service=FakeCandidateService(),
            reup_queue_service=FakeQueueService(),
            capture_inbox_service=object(),
        )

        self.assertEqual(response.total_count, 1009)
        self.assertEqual(response.status_counts[CandidateStatus.SHORTLISTED.value], 925)
        self.assertEqual(sum(response.status_counts.values()), response.total_count)


if __name__ == "__main__":
    unittest.main()
