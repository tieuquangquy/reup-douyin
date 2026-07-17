import inspect
import unittest


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


if __name__ == "__main__":
    unittest.main()
