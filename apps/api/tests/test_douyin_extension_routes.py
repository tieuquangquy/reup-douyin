from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from src.main import app
from src.api.routes.capture_inbox import get_capture_inbox_service
from src.api.routes.douyin_extension import get_douyin_extension_capture_service
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.enums import CapturedItemStatus
from src.schemas.capture_inbox import CaptureSessionCountsResponse


def _full_modal_harvest_payload(**item_overrides):
    item = {
        "aweme_id": "7633842656648416518",
        "metadata_status": "complete",
        "review_status": "pending_review",
        "raw_dom_detail_metrics": {
            "duration_seconds": 12.3,
            "like_count": 100,
            "comment_count": 2,
            "favorite_count": 5,
            "share_count": 1,
            "view_count": None,
            "extraction_source": "dom_detail_modal",
            "confidence": "high",
        },
        "raw_detail_aweme": None,
        "raw_evidence_summary": {
            "has_network_aweme": False,
            "has_detail_aweme": False,
            "has_dom_snapshot": False,
            "has_dom_detail_metrics": True,
            "network_keys": [],
            "detail_keys": [],
            "dom_detail_metric_keys": ["duration_seconds", "like_count", "comment_count", "favorite_count", "share_count", "view_count"],
            "evidence_sources": ["guarded_hybrid_collect_beta", "hybrid_network_cache_payload"],
            "evidence_collection_version": "phase17a_finalized_only_harvest",
        },
    }
    item.update(item_overrides)
    return {
        "schema_version": "douyin_full_modal_harvest.v1",
        "capture_session_id": None,
        "run_id": "guarded-beta-test-run",
        "profile_url": None,
        "target_aweme_id": "7633842656648416518",
        "source_video_external_id": "7633842656648416518",
        "started_at": datetime.now(UTC).isoformat(),
        "page": {"url": None, "title": "Guarded Hybrid Collect Beta", "page_type": "video_detail_page", "video_link_count": 1},
        "capture_context": {"capture_id": "guarded-beta-test-run", "page_url": None, "captured_at": datetime.now(UTC).isoformat()},
        "items": [item],
        "progress": {"running": False, "target_count": 1, "current_aweme_id": "7633842656648416518", "harvested_count": 1, "updated_count": 0, "duplicate_count": 0, "failed_count": 0, "flushed_count": 0, "last_error": None, "stopped_reason": "guarded_hybrid_collect_beta"},
        "commit_policy": "finalized_only",
    }


class DouyinExtensionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        principal = AuthenticatedPrincipal(
            subject="operator@local.test",
            workspace_id=uuid4(),
            roles=("operator",),
            audience="reup-douyin-operator",
        )
        app.dependency_overrides[get_current_principal] = lambda: principal

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_full_modal_harvest_route_is_registered(self) -> None:
        with TestClient(app) as client:
            response = client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/douyin-extension/full-modal-harvest", response.json()["paths"])
        self.assertIn("/douyin-extension/capture-session", response.json()["paths"])
        self.assertIn("/douyin-extension/capture-inbox/shadow-items", response.json()["paths"])
        self.assertIn("/douyin-extension/capture-inbox/profile-summary", response.json()["paths"])

    def test_capture_session_route_accepts_v2_preflight(self) -> None:
        capture_session_id = uuid4()
        recorded = {}

        class StubService:
            def create_capture_session(self, request):
                recorded["request"] = request
                return SimpleNamespace(session_id=capture_session_id, created=True, profile_url=request.profile_url, source=request.source, run_id=request.run_id)

        app.dependency_overrides[get_douyin_extension_capture_service] = lambda: StubService()

        payload = {
            "schema_version": "douyin_extension_capture_session.v1",
            "source": "whole_profile_staged_harvest_v2",
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            "profile_sec_uid_or_path": "MS4wLjABAAAAfixture-sec-uid",
            "source_modal_aweme_id": "7633842656648416518",
            "verified_target_count": 54,
            "run_id": "phase17w-route-run",
            "mode": "whole_profile_staged_harvest_v2",
        }

        with TestClient(app) as client:
            response = client.post("/douyin-extension/capture-session", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], str(capture_session_id))
        self.assertTrue(response.json()["created"])
        self.assertEqual(response.json()["ok"], True)
        self.assertEqual(response.json()["run_id"], "phase17w-route-run")
        self.assertEqual(recorded["request"].run_id, "phase17w-route-run")

    def test_capture_session_route_accepts_canonical_whole_profile_harvest(self) -> None:
        capture_session_id = uuid4()
        recorded = {}

        class StubService:
            def create_capture_session(self, request):
                recorded["request"] = request
                return SimpleNamespace(session_id=capture_session_id, created=True, profile_url=request.profile_url, source=request.source, run_id=request.run_id)

        app.dependency_overrides[get_douyin_extension_capture_service] = lambda: StubService()
        payload = {
            "schema_version": "douyin_extension_capture_session.v1",
            "source": "whole_profile_harvest",
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            "source_modal_aweme_id": None,
            "verified_target_count": 55,
            "run_id": "phase18j-canonical-run",
            "mode": "whole_profile_harvest",
        }

        with TestClient(app) as client:
            response = client.post("/douyin-extension/capture-session", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        self.assertEqual(response.json()["session_id"], str(capture_session_id))
        self.assertEqual(response.json()["source"], "whole_profile_harvest")
        self.assertEqual(response.json()["run_id"], "phase18j-canonical-run")
        self.assertEqual(recorded["request"].source, "whole_profile_harvest")

    def test_full_modal_harvest_route_accepts_one_item(self) -> None:
        capture_session_id = uuid4()
        recorded = {}

        class StubService:
            def ingest_full_modal_harvest(self, request):
                recorded["request"] = request
                return SimpleNamespace(
                    success=True,
                    ok=True,
                    capture_session_id=capture_session_id,
                    capture_inbox_item_id=None,
                    source_video_external_id="7420000000000000001",
                    metadata_status="complete",
                    item_created_or_updated=True,
                    target_count=1,
                    harvested_count=1,
                    matched_count=1,
                    updated_count=1,
                    unchanged_count=0,
                    failed_count=0,
                    duration_updated_count=1,
                    like_updated_count=1,
                    comment_updated_count=1,
                    favorite_updated_count=0,
                    share_updated_count=1,
                    unmatched_count=0,
                    flushed_aweme_ids=["7633842656648416518"],
                    failure_summaries=[],
                    stopped_reason="smoke_test",
                )

        app.dependency_overrides[get_douyin_extension_capture_service] = lambda: StubService()

        payload = {
            "schema_version": "douyin_full_modal_harvest.v1",
            "capture_session_id": str(capture_session_id),
            "started_at": datetime.now(UTC).isoformat(),
            "page": {
                "url": "https://www.douyin.com/video/7633842656648416518",
                "title": "Fixture modal",
                "page_type": "video_detail_page",
                "video_link_count": 1,
            },
            "capture_context": {"page_url": "https://www.douyin.com/video/7633842656648416518"},
            "items": [
                {
                    "aweme_id": "7633842656648416518",
                    "raw_dom_detail_metrics": {
                        "duration_seconds": 563.3,
                        "like_count": 392,
                        "comment_count": 10,
                        "share_count": 1,
                        "extraction_source": "calibrated_point_dom",
                        "confidence": "high",
                    },
                    "raw_detail_aweme": None,
                    "raw_evidence_summary": {
                        "has_network_aweme": False,
                        "has_detail_aweme": False,
                        "has_dom_snapshot": False,
                        "has_dom_detail_metrics": True,
                        "network_keys": [],
                        "detail_keys": [],
                        "dom_detail_metric_keys": ["duration_seconds", "like_count", "comment_count", "share_count"],
                        "evidence_sources": ["smart_capture_harvest", "full_modal_auto_harvest", "calibrated_point_modal_counts", "calibrated_point_dom"],
                        "evidence_collection_version": "phase10a_calibrated_point_extractor",
                    },
                }
            ],
            "progress": {
                "running": False,
                "target_count": 1,
                "current_aweme_id": "7633842656648416518",
                "harvested_count": 1,
                "updated_count": 0,
                "duplicate_count": 0,
                "failed_count": 0,
                "flushed_count": 0,
                "last_error": None,
                "stopped_reason": "smoke_test",
            },
            "diagnostics": {"extension_source": "test"},
        }

        with TestClient(app) as client:
            response = client.post("/douyin-extension/full-modal-harvest", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 1)
        self.assertEqual(recorded["request"].items[0].aweme_id, "7633842656648416518")

    def test_full_modal_harvest_route_accepts_estimated_views_and_nullable_view_count(self) -> None:
        recorded = {}

        class StubService:
            def ingest_full_modal_harvest(self, request):
                recorded["request"] = request
                return SimpleNamespace(
                    success=True,
                    ok=True,
                    capture_session_id=None,
                    capture_inbox_item_id=None,
                    source_video_external_id="7633842656648416518",
                    metadata_status="complete",
                    item_created_or_updated=True,
                    target_count=1,
                    harvested_count=1,
                    matched_count=1,
                    updated_count=1,
                    unchanged_count=0,
                    failed_count=0,
                    duration_updated_count=1,
                    like_updated_count=1,
                    comment_updated_count=1,
                    favorite_updated_count=1,
                    share_updated_count=1,
                    unmatched_count=0,
                    flushed_aweme_ids=["7633842656648416518"],
                    failure_summaries=[],
                    stopped_reason="guarded_hybrid_collect_beta",
                    accepted_count=1,
                    rejected_count=0,
                    estimated_views_received_count=1,
                    estimated_views_persisted_count=1,
                    accepted_not_persisted_count=0,
                    view_count_null_received_count=1,
                    real_view_count_data_quality_received_count=1,
                    estimated_views_accepted_but_not_persisted="no",
                )

        app.dependency_overrides[get_douyin_extension_capture_service] = lambda: StubService()
        payload = _full_modal_harvest_payload(
            view_count=None,
            real_view_count_available=False,
            real_view_count_data_quality="trusted_zero_only_low_confidence",
            estimated_views=3500,
            estimated_views_formula="tiered_like_multiplier_v1",
            estimated_views_used=True,
            real_view_count_overwritten=False,
        )

        with TestClient(app) as client:
            response = client.post("/douyin-extension/full-modal-harvest", json=payload)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorded["request"].items[0].view_count, None)
        self.assertEqual(recorded["request"].items[0].estimated_views, 3500)
        self.assertEqual(body["estimated_views_received_count"], 1)
        self.assertEqual(body["estimated_views_persisted_count"], 1)
        self.assertEqual(body["view_count_null_received_count"], 1)

    def test_full_modal_harvest_route_rejects_estimated_views_copied_to_view_count(self) -> None:
        payload = _full_modal_harvest_payload(
            view_count=3500,
            real_view_count_available=True,
            real_view_count_data_quality="trusted_real_view_count",
            estimated_views=3500,
            estimated_views_formula="tiered_like_multiplier_v1",
            estimated_views_used=True,
            real_view_count_overwritten=False,
        )

        with TestClient(app) as client:
            response = client.post("/douyin-extension/full-modal-harvest", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertIn("estimated_views must not be copied into view_count", response.text)

    def test_full_modal_harvest_route_rejects_invalid_estimated_views(self) -> None:
        payload = _full_modal_harvest_payload(
            view_count=None,
            real_view_count_available=False,
            real_view_count_data_quality="trusted_zero_only_low_confidence",
            estimated_views=-1,
            estimated_views_formula="tiered_like_multiplier_v1",
            estimated_views_used=True,
            real_view_count_overwritten=False,
        )

        with TestClient(app) as client:
            response = client.post("/douyin-extension/full-modal-harvest", json=payload)

        self.assertEqual(response.status_code, 422)

    def test_full_modal_harvest_route_rejects_guarded_beta_diagnostic_fields(self) -> None:
        payload = _full_modal_harvest_payload(
            schema_version="douyin_extension_guarded_hybrid_collect_beta_item.v1",
            view_count=None,
            real_view_count_available=False,
            real_view_count_data_quality="trusted_zero_only_low_confidence",
            estimated_views=3500,
            estimated_views_formula="tiered_like_multiplier_v1",
            estimated_views_used=True,
            real_view_count_overwritten=False,
        )
        payload["write_mode"] = "guarded_hybrid_collect_beta_diagnostic_only"
        payload["source"] = "hybrid_network_cache_payload"
        payload["production_mutation_allowed"] = False

        with TestClient(app) as client:
            response = client.post("/douyin-extension/full-modal-harvest", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertIn("extra_forbidden", response.text)

    def test_shadow_items_route_accepts_low_confidence_zero_suppressed_payload_without_mutation(self) -> None:
        payload = {
            "schema_version": "douyin_extension_shadow_estimated_views.v1",
            "write_mode": "backend_shadow_test",
            "production_mutation_allowed": False,
            "source": "hybrid_only_dry_run",
            "source_run_id": "shadow-run-1",
            "estimated_views_formula": "tiered_like_multiplier_v1",
            "items": [
                {
                    "aweme_id": "7633842656648416518",
                    "source_video_external_id": "7633842656648416518",
                    "duration_seconds": 12.3,
                    "like_count": 100,
                    "comment_count": 2,
                    "favorite_count": 5,
                    "share_count": 1,
                    "posted": "2026-01-01",
                    "posted_at": "2026-01-01T00:00:00Z",
                    "thumbnail_url_present": "yes",
                    "thumbnail_url_host": "example.test",
                    "view_count": None,
                    "real_view_count_available": False,
                    "real_view_count_value": None,
                    "real_view_count_data_quality": "trusted_zero_only_low_confidence",
                    "low_confidence_zero_real_view_count_suppressed": True,
                    "estimated_views": 3500,
                    "estimated_views_formula": "tiered_like_multiplier_v1",
                    "estimated_views_used": True,
                    "real_view_count_overwritten": False,
                    "view_count_data_quality": "trusted_zero_only_low_confidence",
                }
            ],
        }

        with TestClient(app) as client:
            response = client.post("/douyin-extension/capture-inbox/shadow-items", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["accepted_count"], 1)
        self.assertEqual(body["rejected_count"], 0)
        self.assertEqual(body["production_mutation_detected"], "no")
        self.assertEqual(body["production_collect_state_mutated"], "no")
        self.assertEqual(body["production_counters_mutated"], "no")
        self.assertEqual(body["collect_job_mutated"], "no")
        self.assertEqual(body["queue_items_marked_complete"], "no")
        self.assertEqual(body["items"][0]["status"], "accepted")
        self.assertIsNone(body["items"][0]["view_count_received"])
        self.assertEqual(body["items"][0]["estimated_views_received"], 3500)

    def test_shadow_items_route_rejects_low_confidence_zero_sent_as_real(self) -> None:
        payload = {
            "schema_version": "douyin_extension_shadow_estimated_views.v1",
            "write_mode": "backend_shadow_test",
            "production_mutation_allowed": False,
            "source": "hybrid_only_dry_run",
            "estimated_views_formula": "tiered_like_multiplier_v1",
            "items": [
                {
                    "aweme_id": "7633842656648416518",
                    "view_count": 0,
                    "real_view_count_available": False,
                    "real_view_count_value": None,
                    "real_view_count_data_quality": "trusted_zero_only_low_confidence",
                    "low_confidence_zero_real_view_count_suppressed": False,
                    "estimated_views": 3500,
                    "estimated_views_formula": "tiered_like_multiplier_v1",
                    "estimated_views_used": True,
                    "real_view_count_overwritten": False,
                }
            ],
        }

        with TestClient(app) as client:
            response = client.post("/douyin-extension/capture-inbox/shadow-items", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], False)
        self.assertEqual(body["accepted_count"], 0)
        self.assertEqual(body["rejected_count"], 1)
        self.assertIn("low_confidence_zero_view_count_sent_as_real", body["items"][0]["reasons"])
        self.assertEqual(body["production_mutation_detected"], "no")

    def test_classify_targets_route_returns_counts(self) -> None:
        recorded = {}

        class StubService:
            def classify_targets(self, request):
                recorded["request"] = request
                return {
                    "ok": True,
                    "profile_url": request.profile_url,
                    "items": [
                        {
                            "aweme_id": "a1",
                            "source_video_external_id": "a1",
                            "capture_status": "new",
                            "item_id": None,
                            "metadata_status": "missing",
                            "missing_fields": ["source_video"],
                            "existing_fields": {},
                            "updated_at": None,
                        }
                    ],
                    "counts": {"new": 1, "incomplete": 0, "complete": 0, "failed": 0, "skipped": 0, "unknown": 0},
                }

        app.dependency_overrides[get_douyin_extension_capture_service] = lambda: StubService()

        payload = {
            "schema_version": "douyin_extension_target_classification.v1",
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
            "source": "whole_profile_harvest",
            "targets": [{"aweme_id": "a1"}],
        }

        with TestClient(app) as client:
            response = client.post("/douyin-extension/capture-inbox/classify-targets", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["counts"]["new"], 1)
        self.assertEqual(body["items"][0]["capture_status"], "new")
        self.assertEqual(recorded["request"].targets[0].aweme_id, "a1")

    def test_profile_items_route_returns_safe_same_profile_aliases(self) -> None:
        item_id = uuid4()
        session_id = uuid4()
        now = datetime.now(UTC)
        recorded = {}

        class StubService:
            def list_profile_items(self, *, profile_url: str, limit: int = 500, offset: int = 0):
                recorded["profile_url"] = profile_url
                recorded["limit"] = limit
                recorded["offset"] = offset
                return (
                    "MS4wLjABAAAAfixture-sec-uid",
                    "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
                    [
                        SimpleNamespace(
                            id=item_id,
                            capture_session_id=session_id,
                            status=CapturedItemStatus.READY,
                            source_profile_external_id="MS4wLjABAAAAfixture-sec-uid",
                            profile_url="https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid?modal_id=7633842656648416518",
                            source_video_external_id="7633842656648416518",
                            metadata_json={
                                "metadata_status": "complete",
                                "review_status": "ready_for_review",
                                "duration_seconds": 12.5,
                                "like_count": 120,
                                "comment_count": 3,
                                "favorite_count": 4,
                                "share_count": 5,
                                "posted_at": now.isoformat(),
                                "thumbnail_url": "https://example.invalid/thumb.jpg",
                                "estimated_views": 4200,
                                "estimated_views_formula": "tiered_like_multiplier_v1",
                                "real_view_count_data_quality": "trusted_zero_only_low_confidence",
                                "finalized_metadata_source": "guarded_hybrid_network_cache",
                                "raw_secret": "must_not_leak",
                            },
                            created_at=now,
                            updated_at=now,
                        )
                    ],
                    1,
                    1,
                )

            def get_profile_summary(self, *, profile_url: str):
                recorded["summary_profile_url"] = profile_url
                counts = CaptureSessionCountsResponse(captured=1, ready=1, needs_action=0, dup=0, fail=0)
                return (
                    "MS4wLjABAAAAfixture-sec-uid",
                    "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
                    counts,
                    1,
                    1,
                )

        app.dependency_overrides[get_capture_inbox_service] = lambda: StubService()

        with TestClient(app) as client:
            response = client.get(
                "/douyin-extension/capture-inbox/profile-items",
                params={
                    "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid?modal_id=999",
                    "limit": 1000,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorded["profile_url"], "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid?modal_id=999")
        self.assertEqual(recorded["limit"], 1000)
        self.assertEqual(recorded["offset"], 0)
        body = response.json()
        self.assertEqual(body["source"], "capture_inbox_profile_items")
        self.assertEqual(body["profile_scope"], "same_profile_only")
        self.assertEqual(body["total_count"], 1)
        self.assertEqual(body["unique_video_count"], 1)
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["profile_identifier"], "MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(body["normalized_profile_url"], "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(body["items_count"], 1)
        self.assertEqual(body["counts"]["captured"], 1)
        self.assertEqual(body["counts"]["ready"], 1)
        safe_item = body["items"][0]
        self.assertEqual(safe_item["id"], str(item_id))
        self.assertEqual(safe_item["capture_session_id"], str(session_id))
        self.assertEqual(safe_item["aweme_id"], "7633842656648416518")
        self.assertEqual(safe_item["source_video_external_id"], "7633842656648416518")
        self.assertEqual(safe_item["video_external_id"], "7633842656648416518")
        self.assertEqual(safe_item["external_id"], "7633842656648416518")
        self.assertEqual(safe_item["metadata_status"], "complete")
        self.assertEqual(safe_item["review_status"], "ready_for_review")
        self.assertEqual(safe_item["duration_seconds"], 12.5)
        self.assertEqual(safe_item["like_count"], 120)
        self.assertEqual(safe_item["comment_count"], 3)
        self.assertEqual(safe_item["favorite_count"], 4)
        self.assertEqual(safe_item["share_count"], 5)
        self.assertEqual(safe_item["posted_at"], now.isoformat().replace("+00:00", "Z"))
        self.assertEqual(safe_item["thumbnail_url"], "https://example.invalid/thumb.jpg")
        self.assertEqual(safe_item["estimated_views"], 4200)
        self.assertEqual(safe_item["estimated_views_formula"], "tiered_like_multiplier_v1")
        self.assertIsNone(safe_item["view_count"])
        self.assertEqual(safe_item["real_view_count_data_quality"], "trusted_zero_only_low_confidence")
        self.assertEqual(safe_item["finalized_metadata_source"], "guarded_hybrid_network_cache")
        for forbidden in ("metadata_json", "raw_payload_json", "enrichment_json", "raw_html", "headers", "cookies", "tokens", "raw_secret"):
            self.assertNotIn(forbidden, safe_item)

    def test_profile_summary_route_returns_aggregate_counts_above_item_limit(self) -> None:
        recorded = {}

        class StubService:
            def get_profile_summary(self, *, profile_url: str):
                recorded["profile_url"] = profile_url
                counts = CaptureSessionCountsResponse(captured=1500, ready=1400, needs_action=80, dup=10, fail=10)
                return (
                    "MS4wLjABAAAAfixture-sec-uid",
                    "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
                    counts,
                    1500,
                    1490,
                )

        app.dependency_overrides[get_capture_inbox_service] = lambda: StubService()

        with TestClient(app) as client:
            response = client.get(
                "/douyin-extension/capture-inbox/profile-summary",
                params={
                    "profile_url": "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid?modal_id=999",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorded["profile_url"], "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid?modal_id=999")
        body = response.json()
        self.assertEqual(body["source"], "capture_inbox_profile_summary")
        self.assertEqual(body["profile_scope"], "same_profile_only")
        self.assertEqual(body["profile_identifier"], "MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(body["normalized_profile_url"], "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid")
        self.assertEqual(body["total_count"], 1500)
        self.assertEqual(body["unique_video_count"], 1490)
        self.assertEqual(body["counts"]["captured"], 1500)
        self.assertEqual(body["counts"]["ready"], 1400)
        self.assertEqual(body["counts"]["needs_action"], 80)
        self.assertNotIn("items", body)


    def test_verify_items_route_returns_read_only_safe_aweme_lookup(self) -> None:
        item_id = uuid4()
        session_id = uuid4()
        now = datetime.now(UTC)
        recorded = {}

        class StubService:
            def verify_items_by_external_ids(
                self,
                *,
                aweme_ids,
                source_video_external_ids,
                capture_session_id=None,
                profile_url=None,
                limit=100,
            ):
                recorded["aweme_ids"] = aweme_ids
                recorded["source_video_external_ids"] = source_video_external_ids
                recorded["capture_session_id"] = capture_session_id
                recorded["profile_url"] = profile_url
                recorded["limit"] = limit
                return [
                    SimpleNamespace(
                        id=item_id,
                        capture_session_id=session_id,
                        status=CapturedItemStatus.READY,
                        source_video_external_id="7633842656648416518",
                        metadata_json={
                            "metadata_status": "partial",
                            "review_status": "ready_for_review",
                            "duration_seconds": 12.5,
                            "like_count": 120,
                            "comment_count": 3,
                            "favorite_count": 4,
                            "share_count": 5,
                            "posted_at": now.isoformat(),
                            "thumbnail_url": "https://example.invalid/thumb.jpg",
                            "estimated_views": 4200.0,
                            "estimated_views_formula": "tiered_like_multiplier_v1",
                            "real_view_count_data_quality": "trusted_zero_only_low_confidence",
                            "finalized_metadata_source": "guarded_hybrid_network_cache",
                            "profile_card_evidence": {
                                "title": "Real beta fixture title",
                                "caption": "Real beta fixture title",
                            },
                            "raw_secret": "must_not_leak",
                        },
                        raw_payload_json={"title": "7633842656648416518"},
                        created_at=now,
                        updated_at=now,
                    )
                ]

        app.dependency_overrides[get_capture_inbox_service] = lambda: StubService()

        with TestClient(app) as client:
            response = client.post(
                "/douyin-extension/capture-inbox/items/verify",
                json={
                    "aweme_ids": ["7633842656648416518", "missing-aweme"],
                    "source_video_external_ids": ["7633842656648416518"],
                    "capture_session_id": str(session_id),
                    "limit": 3,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(recorded["aweme_ids"], ["7633842656648416518", "missing-aweme"])
        self.assertEqual(recorded["source_video_external_ids"], ["7633842656648416518"])
        self.assertEqual(str(recorded["capture_session_id"]), str(session_id))
        self.assertEqual(recorded["limit"], 3)
        body = response.json()
        self.assertEqual(body["source"], "capture_inbox_items_verify")
        self.assertEqual(body["read_only"], True)
        self.assertEqual(body["requested_count"], 2)
        self.assertEqual(body["found_count"], 1)
        self.assertEqual(body["missing_count"], 1)
        safe_item = body["items"][0]
        self.assertEqual(safe_item["found"], True)
        self.assertEqual(safe_item["id"], str(item_id))
        self.assertEqual(safe_item["capture_inbox_item_id"], str(item_id))
        self.assertEqual(safe_item["aweme_id"], "7633842656648416518")
        self.assertEqual(safe_item["source_video_external_id"], "7633842656648416518")
        self.assertEqual(safe_item["title"], "Real beta fixture title")
        self.assertEqual(safe_item["caption"], "Real beta fixture title")
        self.assertEqual(safe_item["duration_seconds"], 12.5)
        self.assertEqual(safe_item["like_count"], 120)
        self.assertEqual(safe_item["comment_count"], 3)
        self.assertEqual(safe_item["favorite_count"], 4)
        self.assertEqual(safe_item["share_count"], 5)
        self.assertEqual(safe_item["posted_at"], now.isoformat().replace("+00:00", "Z"))
        self.assertEqual(safe_item["thumbnail_url"], "https://example.invalid/thumb.jpg")
        self.assertIsNone(safe_item["view_count"])
        self.assertEqual(safe_item["estimated_views"], 4200)
        self.assertEqual(safe_item["estimated_views_formula"], "tiered_like_multiplier_v1")
        self.assertEqual(safe_item["real_view_count_data_quality"], "trusted_zero_only_low_confidence")
        self.assertEqual(safe_item["metadata_status"], "partial")
        self.assertEqual(safe_item["review_status"], "ready_for_review")
        for forbidden in ("metadata_json", "raw_payload_json", "enrichment_json", "raw_html", "headers", "cookies", "tokens", "raw_secret"):
            self.assertNotIn(forbidden, safe_item)


if __name__ == "__main__":
    unittest.main()
