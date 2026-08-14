from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from src.main import app
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.schemas.douyin_extension import DouyinProfileVideoCandidate
from src.db.session import get_db_session
from src.services.douyin_profile_classification_service import classify_douyin_profile_candidates


class EmptyReadOnlyDb:
    def __init__(self) -> None:
        self.write_calls: list[str] = []

    def scalars(self, _stmt):
        return []

    def add(self, _obj) -> None:
        self.write_calls.append("add")

    def commit(self) -> None:
        self.write_calls.append("commit")

    def flush(self) -> None:
        self.write_calls.append("flush")


class DouyinProfileVideoClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        principal = AuthenticatedPrincipal(
            subject="operator@local.test",
            workspace_id=uuid4(),
            roles=("operator",),
            audience="reup-douyin-operator",
        )
        app.dependency_overrides[get_current_principal] = lambda: principal
        # Route-contract tests are read-only and must not depend on whichever
        # process-global database URL another test module configured.
        app.dependency_overrides[get_db_session] = lambda: EmptyReadOnlyDb()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def _candidate(self, aweme_id: str = "7635294267413368100") -> DouyinProfileVideoCandidate:
        return DouyinProfileVideoCandidate(
            aweme_id=aweme_id,
            video_url=f"https://www.douyin.com/video/{aweme_id}" if aweme_id else None,
            source_url=f"https://www.douyin.com/user/xxx?modal_id={aweme_id}" if aweme_id else None,
            thumbnail_url="https://example.test/thumb.jpg",
            caption="some title",
        )

    def _complete_record(self, aweme_id: str = "7635294267413368100") -> dict:
        return {
            "id": "item_1",
            "aweme_id": aweme_id,
            "metadata_status": "ready",
            "review_status": "pending_review",
            "duration_seconds": 123,
            "duration_text": "02:03",
            "like_count": 100,
            "comment_count": 10,
            "favorite_count": 5,
            "share_count": 2,
        }

    def _classify(self, candidates, existing_index=None, mode="new_incomplete_failed", include_unknown=False):
        return classify_douyin_profile_candidates(
            candidates,
            existing_index or {},
            mode,
            include_unknown=include_unknown,
        )

    def test_missing_existing_record_is_new_and_collected_by_default(self) -> None:
        result = self._classify([self._candidate()])
        self.assertEqual(result["targets"][0].classification, "new")
        self.assertTrue(result["targets"][0].collect)
        self.assertEqual(result["targets"][0].reason, "not_found_in_existing_index")

    def test_existing_complete_record_is_skipped_by_default(self) -> None:
        candidate = self._candidate()
        result = self._classify([candidate], {candidate.aweme_id: self._complete_record(candidate.aweme_id)})
        self.assertEqual(result["targets"][0].classification, "complete")
        self.assertFalse(result["targets"][0].collect)

    def test_existing_incomplete_record_is_collected_by_default(self) -> None:
        candidate = self._candidate()
        record = self._complete_record(candidate.aweme_id)
        record["duration_seconds"] = None
        record["duration_text"] = ""
        result = self._classify([candidate], {candidate.aweme_id: record})
        self.assertEqual(result["targets"][0].classification, "incomplete")
        self.assertTrue(result["targets"][0].collect)

    def test_existing_failed_record_is_collected_by_default(self) -> None:
        candidate = self._candidate()
        record = self._complete_record(candidate.aweme_id)
        record["metadata_status"] = "failed"
        result = self._classify([candidate], {candidate.aweme_id: record})
        self.assertEqual(result["targets"][0].classification, "failed")
        self.assertTrue(result["targets"][0].collect)

    def test_existing_skipped_record_is_not_collected(self) -> None:
        candidate = self._candidate()
        record = self._complete_record(candidate.aweme_id)
        record["metadata_status"] = "skipped"
        result = self._classify([candidate], {candidate.aweme_id: record}, mode="refresh_all")
        self.assertEqual(result["targets"][0].classification, "skipped")
        self.assertFalse(result["targets"][0].collect)

    def test_refresh_all_collects_complete_records(self) -> None:
        candidate = self._candidate()
        result = self._classify([candidate], {candidate.aweme_id: self._complete_record(candidate.aweme_id)}, mode="refresh_all")
        self.assertEqual(result["targets"][0].classification, "complete")
        self.assertTrue(result["targets"][0].collect)

    def test_new_only_collects_only_new(self) -> None:
        new_candidate = self._candidate("new-1")
        complete_candidate = self._candidate("complete-1")
        result = self._classify(
            [new_candidate, complete_candidate],
            {complete_candidate.aweme_id: self._complete_record(complete_candidate.aweme_id)},
            mode="new_only",
        )
        self.assertEqual(result["collect_aweme_ids"], ["new-1"])
        self.assertEqual(result["skip_aweme_ids"], ["complete-1"])

    def test_failed_only_collects_only_failed(self) -> None:
        failed_candidate = self._candidate("failed-1")
        new_candidate = self._candidate("new-1")
        record = self._complete_record(failed_candidate.aweme_id)
        record["metadata_status"] = "error"
        result = self._classify([failed_candidate, new_candidate], {failed_candidate.aweme_id: record}, mode="failed_only")
        self.assertEqual(result["collect_aweme_ids"], ["failed-1"])
        self.assertEqual(result["skip_aweme_ids"], ["new-1"])

    def test_missing_duration_reports_duration_missing_field(self) -> None:
        candidate = self._candidate()
        record = self._complete_record(candidate.aweme_id)
        record["duration_seconds"] = None
        record["duration_text"] = None
        result = self._classify([candidate], {candidate.aweme_id: record})
        self.assertIn("duration", result["targets"][0].required_missing_fields)

    def test_missing_engagement_counts_report_missing_fields(self) -> None:
        candidate = self._candidate()
        record = self._complete_record(candidate.aweme_id)
        for field in ("like_count", "comment_count", "favorite_count", "share_count"):
            record[field] = None
        result = self._classify([candidate], {candidate.aweme_id: record})
        self.assertEqual(
            result["targets"][0].required_missing_fields,
            ["like_count", "comment_count", "favorite_count", "share_count"],
        )

    def test_duplicate_candidates_keep_first_and_count_diagnostic(self) -> None:
        result = self._classify([self._candidate("dup-1"), self._candidate("dup-1")])
        self.assertEqual(len(result["targets"]), 1)
        self.assertEqual(result["collect_aweme_ids"], ["dup-1"])
        self.assertEqual(result["diagnostics"]["duplicate_candidate_count"], 1)

    def test_invalid_empty_aweme_id_returns_unknown(self) -> None:
        result = self._classify([self._candidate("")])
        self.assertEqual(result["targets"][0].classification, "unknown")
        self.assertEqual(result["targets"][0].reason, "invalid_aweme_id")
        self.assertEqual(result["diagnostics"]["invalid_candidate_count"], 1)

    def test_include_unknown_false_skips_unknown(self) -> None:
        result = self._classify([self._candidate("")], include_unknown=False)
        self.assertFalse(result["targets"][0].collect)

    def test_include_unknown_true_collects_unknown(self) -> None:
        result = self._classify([self._candidate("")], include_unknown=True)
        self.assertTrue(result["targets"][0].collect)

    def test_post_valid_request_returns_result_schema_version(self) -> None:
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=self._valid_payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema_version"], "douyin_profile_video_classification_result.v1")

    def test_post_valid_request_returns_counts(self) -> None:
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=self._valid_payload())
        body = response.json()
        self.assertEqual(body["counts"]["new"], 1)
        self.assertEqual(body["counts"]["collect"], 1)
        self.assertEqual(body["total_candidates"], 1)

    def test_post_valid_request_returns_collect_aweme_ids(self) -> None:
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=self._valid_payload())
        self.assertEqual(response.json()["collect_aweme_ids"], ["7635294267413368100"])

    def test_endpoint_uses_read_only_database_lookup(self) -> None:
        db = EmptyReadOnlyDb()
        app.dependency_overrides[get_db_session] = lambda: db
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=self._valid_payload())
        body = response.json()
        self.assertEqual(body["database_lookup_status"], "ok")
        self.assertFalse(body["diagnostics"]["contract_only"])
        self.assertTrue(body["diagnostics"]["db_lookup_enabled"])
        self.assertTrue(body["diagnostics"]["read_only"])
        self.assertEqual(db.write_calls, [])

    def test_wrong_schema_version_returns_422(self) -> None:
        payload = self._valid_payload()
        payload["schema_version"] = "wrong.v1"
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_response_does_not_create_capture_inbox_items_or_scan_sessions(self) -> None:
        db = EmptyReadOnlyDb()
        app.dependency_overrides[get_db_session] = lambda: db
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=self._valid_payload())
        body = response.json()
        self.assertNotIn("capture_session_id", body)
        self.assertNotIn("captured_item_count", body)
        self.assertEqual(body["database_lookup_status"], "ok")
        self.assertEqual(db.write_calls, [])

    def _valid_payload(self) -> dict:
        return {
            "schema_version": "douyin_profile_video_classification.v1",
            "profile_url": "https://www.douyin.com/user/xxx",
            "sec_uid": "MS4wLjAB...",
            "collection_mode": "new_incomplete_failed",
            "candidates": [
                {
                    "aweme_id": "7635294267413368100",
                    "video_url": "https://www.douyin.com/video/7635294267413368100",
                    "source_url": "https://www.douyin.com/user/xxx?modal_id=7635294267413368100",
                    "thumbnail_url": "https://example.test/thumb.jpg",
                    "caption": "some title",
                    "posted_text": "3天前",
                    "view_count": None,
                }
            ],
            "include_unknown": False,
            "dry_run": True,
        }


if __name__ == "__main__":
    unittest.main()
