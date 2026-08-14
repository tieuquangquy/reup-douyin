from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.routes.capture_inbox import get_capture_inbox_service
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.core.settings import get_settings
from src.enums import CapturedItemStatus
from src.main import create_app


class CaptureInboxItemDetailRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        self.app = create_app()
        self.item_id = uuid4()
        self.session_id = uuid4()
        self.workspace_id = uuid4()
        self.now = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)
        # This suite tests the Capture Inbox route contract, not login or DB
        # seeding. Override the router-level principal so it remains a true unit
        # test and cannot depend on a process-global SQLite database.
        principal = AuthenticatedPrincipal(
            subject="operator@local.test",
            workspace_id=self.workspace_id,
            roles=("operator",),
            audience="reup-douyin-operator",
        )
        self.app.dependency_overrides[get_current_principal] = lambda: principal

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        get_settings.cache_clear()

    def _auth_headers(self, client: TestClient) -> dict[str, str]:
        del client
        return {}

    def test_get_captured_item_returns_full_inspector_fields(self) -> None:
        item_id = self.item_id
        item = SimpleNamespace(
            id=self.item_id,
            workspace_id=uuid4(),
            capture_session_id=self.session_id,
            source_platform="DOUYIN",
            raw_item_index=0,
            status=CapturedItemStatus.READY,
            source_video_external_id="7633842656648416518",
            caption="Fixture caption",
            metadata_json={
                "metadata_status": "complete",
                "duration_source": "dom_detail_modal",
                "posted_source": "dom_detail_modal",
                "view_count_source": "dom_detail_modal",
                "like_count_source": "dom_detail_modal",
                "comment_count_source": "dom_zero_sentinel",
                "share_count_source": "dom_zero_sentinel",
                "time_status": "captured",
                "performance_status": "captured",
                "processing_fit_status": "pending",
                "metadata_source_summary": "dom_detail_modal + dom_zero_sentinel",
                "duration_seconds": 741.0,
                "posted_at": self.now.isoformat(),
                "thumbnail_url": "https://example.invalid/thumb.jpg",
                "like_count": 32000,
                "comment_count": 0,
                "share_count": 0,
            },
            raw_payload_json={"statistics": {"play_count": 697300}},
            enrichment_json=None,
            created_at=self.now,
            updated_at=self.now,
        )

        class StubService:
            def get_item(self, requested_id):
                if requested_id != item_id:
                    raise AssertionError(f"unexpected item id {requested_id}")
                return item

        self.app.dependency_overrides[get_capture_inbox_service] = StubService

        with TestClient(self.app) as client:
            response = client.get(f"/capture-inbox/items/{self.item_id}", headers=self._auth_headers(client))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], str(self.item_id))
        self.assertIn(body["metadata_status"], {"complete", "partial"})
        self.assertEqual(body["time_status"], "captured")
        self.assertEqual(body["performance_status"], "captured")
        self.assertEqual(body["duration_source"], "dom_detail_modal")
        self.assertEqual(body["comment_count_source"], "dom_zero_sentinel")
        self.assertEqual(body["metadata_source_summary"], "dom_detail_modal + dom_zero_sentinel")
        self.assertIsInstance(body["metadata_json"], dict)
        self.assertIsInstance(body["raw_payload_json"], dict)

    def test_get_captured_item_returns_404_when_missing(self) -> None:
        from src.services.capture_inbox_service import CaptureInboxError

        class StubService:
            def get_item(self, item_id):
                raise CaptureInboxError("captured_item_not_found", f"Captured item {item_id} was not found.")

        self.app.dependency_overrides[get_capture_inbox_service] = StubService

        with TestClient(self.app) as client:
            response = client.get(f"/capture-inbox/items/{uuid4()}", headers=self._auth_headers(client))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "captured_item_not_found")


if __name__ == "__main__":
    unittest.main()
