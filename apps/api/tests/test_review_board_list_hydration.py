import inspect
import unittest

from src.services import candidate_service


class ReviewBoardListHydrationTests(unittest.TestCase):
    def test_list_candidates_hydrates_only_returned_page_not_entire_board(self) -> None:
        source = inspect.getsource(candidate_service.CandidateEvaluationService.list_candidates)

        self.assertNotIn("_hydrate_stale_candidates_from_capture_inbox()", source)
        self.assertIn("hydrateReviewCandidateFromCaptureItem", source)

    def test_list_candidates_skips_already_hydrated_candidates(self) -> None:
        source = inspect.getsource(candidate_service.CandidateEvaluationService)

        self.assertIn("def _should_hydrate_review_board_candidate", source)
        self.assertIn("_should_hydrate_review_board_candidate(candidate)", source)


if __name__ == "__main__":
    unittest.main()
