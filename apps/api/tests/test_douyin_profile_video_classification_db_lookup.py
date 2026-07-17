from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.routes.douyin_extension import get_db_session
from src.enums import CapturedItemStatus, SourceVideoStatus
from src.main import app
from src.services.douyin_profile_classification_service import (
    build_douyin_profile_video_classification_response,
    lookup_existing_douyin_video_index,
    map_capture_inbox_item_to_classification_record,
    map_source_video_to_classification_record,
)


class ReadOnlyRowsDb:
    def __init__(self, capture_rows=None, source_rows=None, fail: bool = False) -> None:
        self.capture_rows = list(capture_rows or [])
        self.source_rows = list(source_rows or [])
        self.fail = fail
        self.calls = 0
        self.write_calls: list[str] = []

    def scalars(self, _stmt):
        if self.fail:
            raise RuntimeError("lookup failed")
        self.calls += 1
        return self.capture_rows if self.calls == 1 else self.source_rows

    def add(self, _obj) -> None:
        self.write_calls.append("add")

    def commit(self) -> None:
        self.write_calls.append("commit")

    def flush(self) -> None:
        self.write_calls.append("flush")


def capture_item(**overrides):
    data = {
        "id": uuid4(),
        "source_video_external_id": "7635294267413368100",
        "profile_url": "https://www.douyin.com/user/xxx",
        "status": CapturedItemStatus.READY,
        "duration_seconds": 12.5,
        "caption": "caption",
        "thumbnail_url": "https://example.test/thumb.jpg",
        "source_url": "https://www.douyin.com/video/7635294267413368100",
        "metadata_json": {"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4},
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def source_video(**overrides):
    data = {
        "id": uuid4(),
        "source_video_external_id": "7635294267413368100",
        "status": SourceVideoStatus.DISCOVERED,
        "duration_seconds": 12.5,
        "caption": "canonical caption",
        "source_url": "https://www.douyin.com/video/7635294267413368100",
        "metadata_json": {"like_count": 1, "comment_count": 2, "favorite_count": 3, "share_count": 4},
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 3, tzinfo=UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class DouyinProfileVideoClassificationDbLookupTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_maps_capture_inbox_item_to_complete_record(self) -> None:
        record = map_capture_inbox_item_to_classification_record(capture_item())
        self.assertEqual(record["source_video_external_id"], "7635294267413368100")
        self.assertEqual(record["metadata_status"], "ready")
        self.assertEqual(record["favorite_count"], 3)

    def test_maps_failed_capture_inbox_item_to_failed_record(self) -> None:
        record = map_capture_inbox_item_to_classification_record(capture_item(status=CapturedItemStatus.FAILED, metadata_json={}))
        self.assertEqual(record["metadata_status"], "failed")

    def test_maps_excluded_capture_inbox_item_to_skipped_record(self) -> None:
        record = map_capture_inbox_item_to_classification_record(capture_item(status=CapturedItemStatus.EXCLUDED, metadata_json={}))
        self.assertEqual(record["metadata_status"], "skipped")

    def test_maps_source_video_to_complete_record(self) -> None:
        record = map_source_video_to_classification_record(source_video())
        self.assertEqual(record["record_source"], "source_video")
        self.assertEqual(record["metadata_status"], "ready")

    def test_maps_failed_source_video_to_failed_record(self) -> None:
        record = map_source_video_to_classification_record(source_video(status=SourceVideoStatus.FAILED))
        self.assertEqual(record["metadata_status"], "failed")

    def test_lookup_returns_capture_inbox_record_by_aweme_id(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[capture_item()], source_rows=[])
        index = lookup_existing_douyin_video_index(db=db, candidate_aweme_ids=["7635294267413368100"])
        self.assertIn("7635294267413368100", index)
        self.assertEqual(index["7635294267413368100"]["record_source"], "capture_inbox")
        self.assertEqual(db.write_calls, [])

    def test_lookup_returns_source_video_record_by_aweme_id(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[], source_rows=[source_video()])
        index = lookup_existing_douyin_video_index(db=db, candidate_aweme_ids=["7635294267413368100"])
        self.assertEqual(index["7635294267413368100"]["record_source"], "source_video")

    def test_lookup_deduplicates_candidate_ids(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[], source_rows=[])
        index = lookup_existing_douyin_video_index(db=db, candidate_aweme_ids=["", "a1", "a1", " a1 "])
        self.assertEqual(index, {})
        self.assertEqual(db.calls, 2)

    def test_lookup_prefers_complete_record_over_incomplete(self) -> None:
        incomplete = capture_item(metadata_json={"like_count": 1}, updated_at=datetime(2026, 1, 4, tzinfo=UTC))
        complete = source_video(updated_at=datetime(2026, 1, 3, tzinfo=UTC))
        db = ReadOnlyRowsDb(capture_rows=[incomplete], source_rows=[complete])
        index = lookup_existing_douyin_video_index(db=db, candidate_aweme_ids=["7635294267413368100"])
        self.assertEqual(index["7635294267413368100"]["record_source"], "source_video")

    def test_response_classifies_existing_complete_as_skipped_by_default(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[capture_item()], source_rows=[])
        response = build_douyin_profile_video_classification_response(
            db=db,
            profile_url="https://www.douyin.com/user/xxx",
            sec_uid=None,
            collection_mode="new_incomplete_failed",
            candidates=[SimpleNamespace(aweme_id="7635294267413368100", video_url=None, source_url=None, thumbnail_url=None, caption=None)],
        )
        self.assertEqual(response.database_lookup_status, "ok")
        self.assertEqual(response.targets[0].classification, "complete")
        self.assertFalse(response.targets[0].collect)
        self.assertEqual(response.diagnostics["existing_match_count"], 1)
        self.assertTrue(response.diagnostics["read_only"])

    def test_response_classifies_existing_incomplete_as_collect(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[capture_item(metadata_json={"like_count": 1, "comment_count": 2})], source_rows=[])
        response = build_douyin_profile_video_classification_response(
            db=db,
            profile_url="https://www.douyin.com/user/xxx",
            sec_uid=None,
            collection_mode="new_incomplete_failed",
            candidates=[SimpleNamespace(aweme_id="7635294267413368100", video_url=None, source_url=None, thumbnail_url=None, caption=None)],
        )
        self.assertEqual(response.targets[0].classification, "incomplete")
        self.assertTrue(response.targets[0].collect)
        self.assertIn("favorite_count", response.targets[0].required_missing_fields)

    def test_response_classifies_existing_failed_as_collect(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[capture_item(status=CapturedItemStatus.FAILED, metadata_json={})], source_rows=[])
        response = build_douyin_profile_video_classification_response(
            db=db,
            profile_url="https://www.douyin.com/user/xxx",
            sec_uid=None,
            collection_mode="new_incomplete_failed",
            candidates=[SimpleNamespace(aweme_id="7635294267413368100", video_url=None, source_url=None, thumbnail_url=None, caption=None)],
        )
        self.assertEqual(response.targets[0].classification, "failed")
        self.assertTrue(response.targets[0].collect)

    def test_endpoint_uses_real_lookup_dependency(self) -> None:
        app.dependency_overrides[get_db_session] = lambda: ReadOnlyRowsDb(capture_rows=[capture_item()], source_rows=[])
        payload = {
            "schema_version": "douyin_profile_video_classification.v1",
            "profile_url": "https://www.douyin.com/user/xxx",
            "candidates": [{"aweme_id": "7635294267413368100"}],
        }
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["database_lookup_status"], "ok")
        self.assertFalse(body["diagnostics"]["contract_only"])
        self.assertEqual(body["targets"][0]["classification"], "complete")

    def test_endpoint_returns_500_on_lookup_failure(self) -> None:
        app.dependency_overrides[get_db_session] = lambda: ReadOnlyRowsDb(fail=True)
        payload = {
            "schema_version": "douyin_profile_video_classification.v1",
            "profile_url": "https://www.douyin.com/user/xxx",
            "candidates": [{"aweme_id": "7635294267413368100"}],
        }
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "profile_video_classification_lookup_failed")

    def test_endpoint_remains_read_only(self) -> None:
        db = ReadOnlyRowsDb(capture_rows=[capture_item()], source_rows=[])
        app.dependency_overrides[get_db_session] = lambda: db
        payload = {
            "schema_version": "douyin_profile_video_classification.v1",
            "profile_url": "https://www.douyin.com/user/xxx",
            "candidates": [{"aweme_id": "7635294267413368100"}],
        }
        with TestClient(app) as client:
            response = client.post("/douyin-extension/profile-video-classification", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.write_calls, [])


if __name__ == "__main__":
    unittest.main()
