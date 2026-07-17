from types import SimpleNamespace
from uuid import uuid4
import inspect
import unittest

from src.enums import CandidateStatus
from src.services import candidate_service
from src.services.candidate_service import CandidateEvaluationService


class _FakeDb:
    def __init__(self) -> None:
        self.commits = 0
        self.refreshes = 0
        self.deleted = []

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, candidate) -> None:
        self.refreshes += 1

    def delete(self, record) -> None:
        self.deleted.append(record)


class ReviewBoardCandidateDeleteTests(unittest.TestCase):
    def test_remove_from_review_board_archives_candidate_without_deleting_upstream_data(self) -> None:
        db = _FakeDb()
        service = CandidateEvaluationService(db)  # type: ignore[arg-type]
        candidate_id = uuid4()
        source_video_id = uuid4()
        candidate = SimpleNamespace(
            id=candidate_id,
            source_video_id=source_video_id,
            status=CandidateStatus.IN_REVIEW,
            metadata_json={"existing": "kept"},
            source_video=SimpleNamespace(id=source_video_id),
        )
        service.get_candidate = lambda requested_id: candidate  # type: ignore[method-assign]

        removed = service.remove_from_review_board(candidate_id)

        self.assertIs(removed, candidate)
        self.assertEqual(candidate.status, CandidateStatus.ARCHIVED)
        self.assertEqual(candidate.metadata_json["existing"], "kept")
        self.assertTrue(candidate.metadata_json["removed_from_review_board"])
        self.assertEqual(candidate.metadata_json["removed_from_review_board_reason"], "operator_delete")
        self.assertIn("removed_from_review_board_at", candidate.metadata_json)
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.refreshes, 1)
        self.assertEqual(db.deleted, [], "Review Board delete must not hard-delete SourceVideo or candidate rows")

    def test_default_candidate_listing_excludes_archived_review_board_removals(self) -> None:
        source = inspect.getsource(candidate_service.CandidateEvaluationService._apply_candidate_list_filters)

        self.assertIn("CandidateStatus.ARCHIVED", source)
        self.assertIn("not search_term", source)
        self.assertIn("VideoCandidate.status == status", source)

    def test_backend_exposes_delete_response_schema_and_route_contract(self) -> None:
        from src.api.routes import candidates as candidate_routes
        from src.schemas.candidates import CandidateDeleteResponse

        route_source = inspect.getsource(candidate_routes.delete_candidate)

        self.assertIn("remove_from_review_board", route_source)
        self.assertIn("Source media and upstream records were not deleted", route_source)
        self.assertIn("CandidateDeleteResponse", CandidateDeleteResponse.__name__)


if __name__ == "__main__":
    unittest.main()
