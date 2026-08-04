from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from uuid import uuid4

from pydantic import ValidationError

from src.analytics.services.publication_metrics_helpers import (
    MIN_STABLE_VELOCITY_INTERVAL_SECONDS,
    build_growth_summary,
    canonical_payload_hash,
    recompute_snapshot_series,
)
from src.analytics.services.publication_metrics_service import (
    PublicationMetricsError,
    PublicationMetricsService,
)
from src.models.publish import PlatformPublication
from src.schemas.analytics import PublicationMetricSnapshotCreateRequest


def _row(observed_at: datetime, **metrics):
    defaults = {
        "view_count": None,
        "like_count": None,
        "comment_count": None,
        "share_count": None,
        "save_count": None,
        "data_quality": "COMPLETE",
        "is_estimated": False,
    }
    defaults.update(metrics)
    return SimpleNamespace(id=uuid4(), observed_at=observed_at, **defaults)


class _ExistingSnapshotSession:
    def __init__(self, publication, snapshot):
        self.publication = publication
        self.snapshot = snapshot

    def get(self, model, object_id):
        if model is PlatformPublication and object_id == self.publication.id:
            return self.publication
        return None

    def scalar(self, _statement):
        return self.snapshot


class PublicationMetricSchemaTests(unittest.TestCase):
    def test_snapshot_requires_timezone_and_at_least_one_metric(self) -> None:
        with self.assertRaises(ValidationError):
            PublicationMetricSnapshotCreateRequest(
                observed_at=datetime(2026, 7, 28, 8, 0),
                idempotency_key="sample-1",
                view_count=10,
            )
        with self.assertRaises(ValidationError):
            PublicationMetricSnapshotCreateRequest(
                observed_at=datetime(2026, 7, 28, 8, 0, tzinfo=UTC),
                idempotency_key="sample-2",
            )

    def test_payload_hash_is_order_independent(self) -> None:
        self.assertEqual(
            canonical_payload_hash({"view_count": 10, "nested": {"like_count": 2}}),
            canonical_payload_hash({"nested": {"like_count": 2}, "view_count": 10}),
        )


class PublicationMetricDerivationTests(unittest.TestCase):
    def test_short_interval_does_not_extrapolate_noisy_views_per_hour(self) -> None:
        start = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        first = _row(start, view_count=107, like_count=1)
        second = _row(start + timedelta(seconds=284), view_count=108, like_count=1)

        recompute_snapshot_series([first, second])
        summary = build_growth_summary(uuid4(), [first, second], now=second.observed_at)

        self.assertEqual(second.delta_view_count, 1)
        self.assertIsNone(second.views_per_hour)
        self.assertIsNone(summary["recent_views_per_hour"])
        self.assertIsNone(summary["views_per_hour_since_first"])
        self.assertEqual(summary["trend_label"], "INSUFFICIENT_DATA")
        self.assertEqual(summary["velocity_status"], "INSUFFICIENT_INTERVAL")
        self.assertEqual(
            summary["minimum_velocity_interval_seconds"],
            MIN_STABLE_VELOCITY_INTERVAL_SECONDS,
        )
        self.assertEqual(
            summary["next_stable_measurement_at"],
            start + timedelta(seconds=MIN_STABLE_VELOCITY_INTERVAL_SECONDS),
        )

    def test_recent_velocity_uses_newest_anchor_at_least_thirty_minutes_away(self) -> None:
        start = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        first = _row(start, view_count=100)
        too_close = _row(start + timedelta(minutes=10), view_count=103)
        latest = _row(start + timedelta(minutes=45), view_count=118)

        recompute_snapshot_series([first, too_close, latest])
        summary = build_growth_summary(uuid4(), [first, too_close, latest], now=latest.observed_at)

        self.assertEqual(latest.delta_view_count, 15)
        self.assertAlmostEqual(latest.views_per_hour, 25.714286)
        self.assertAlmostEqual(summary["recent_views_per_hour"], 25.714286)
        self.assertEqual(summary["velocity_observation_seconds"], 35 * 60)
        self.assertEqual(summary["velocity_status"], "STABLE")

    def test_recomputes_velocity_and_engagement_delta(self) -> None:
        start = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        first = _row(start, view_count=100, like_count=10, comment_count=2, share_count=1, save_count=1)
        second = _row(
            start + timedelta(hours=2),
            view_count=300,
            like_count=30,
            comment_count=5,
            share_count=3,
            save_count=2,
        )

        recompute_snapshot_series([second, first])

        self.assertEqual(second.interval_seconds, 7200)
        self.assertEqual(second.delta_view_count, 200)
        self.assertEqual(second.views_per_hour, 100.0)
        self.assertEqual(second.engagement_delta_rate_percent, 13.0)
        self.assertFalse(second.counter_regression_detected)

    def test_late_backfill_recomputes_the_following_snapshot(self) -> None:
        start = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        first = _row(start, view_count=100)
        latest = _row(start + timedelta(hours=2), view_count=300)
        recompute_snapshot_series([first, latest])
        self.assertEqual(latest.delta_view_count, 200)

        backfill = _row(start + timedelta(hours=1), view_count=240)
        recompute_snapshot_series([latest, backfill, first])

        self.assertEqual(backfill.delta_view_count, 140)
        self.assertEqual(latest.delta_view_count, 60)
        self.assertEqual(latest.views_per_hour, 60.0)

    def test_counter_decrease_is_flagged_and_not_given_velocity(self) -> None:
        start = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        first = _row(start, view_count=300, like_count=30)
        latest = _row(start + timedelta(hours=1), view_count=290, like_count=29)

        recompute_snapshot_series([first, latest])

        self.assertTrue(latest.counter_regression_detected)
        self.assertEqual(latest.delta_view_count, -10)
        self.assertIsNone(latest.views_per_hour)
        summary = build_growth_summary(uuid4(), [first, latest], now=start + timedelta(hours=2))
        self.assertEqual(summary["trend_label"], "COUNTER_REGRESSION")

    def test_growth_summary_uses_first_and_latest_snapshots(self) -> None:
        start = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        first = _row(start, view_count=100, like_count=10)
        latest = _row(start + timedelta(hours=4), view_count=500, like_count=50)
        recompute_snapshot_series([first, latest])

        summary = build_growth_summary(uuid4(), [first, latest], now=start + timedelta(hours=5))

        self.assertEqual(summary["snapshot_count"], 2)
        self.assertEqual(summary["absolute_view_growth"], 400)
        self.assertEqual(summary["views_per_hour_since_first"], 100.0)
        self.assertEqual(summary["measurement_age_seconds"], 3600)
        self.assertEqual(summary["trend_label"], "GROWING")


class PublicationMetricIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publication = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
        self.request = PublicationMetricSnapshotCreateRequest(
            observed_at=datetime(2026, 7, 28, 8, 0, tzinfo=UTC),
            collection_source="LOCAL_MOCK",
            idempotency_key="provider:post-1:2026-07-28T08:00:00Z",
            view_count=100,
            like_count=10,
            data_quality="COMPLETE",
        )
        self.payload_hash = PublicationMetricsService._request_payload_hash(self.request)

    def test_same_idempotency_key_and_payload_returns_existing_snapshot(self) -> None:
        existing = SimpleNamespace(payload_hash_sha256=self.payload_hash)
        service = PublicationMetricsService(_ExistingSnapshotSession(self.publication, existing))  # type: ignore[arg-type]

        result = service.record_snapshot(self.publication.id, self.request)

        self.assertIs(result, existing)

    def test_same_idempotency_key_with_different_payload_fails_closed(self) -> None:
        existing = SimpleNamespace(payload_hash_sha256="0" * 64)
        service = PublicationMetricsService(_ExistingSnapshotSession(self.publication, existing))  # type: ignore[arg-type]

        with self.assertRaises(PublicationMetricsError) as context:
            service.record_snapshot(self.publication.id, self.request)

        self.assertEqual(context.exception.code, "metric_snapshot_idempotency_conflict")

    def test_sensitive_provider_summary_is_rejected(self) -> None:
        request = self.request.model_copy(
            update={"provider_summary_json": {"authorization": "Bearer should-never-be-stored"}}
        )
        session = _ExistingSnapshotSession(self.publication, None)
        service = PublicationMetricsService(session)  # type: ignore[arg-type]

        with self.assertRaises(PublicationMetricsError) as context:
            service.record_snapshot(self.publication.id, request)

        self.assertEqual(context.exception.code, "sensitive_metric_summary_rejected")


class PublicationMetricOpenApiTests(unittest.TestCase):
    def test_metric_routes_are_registered(self) -> None:
        from src.main import app

        paths = app.openapi()["paths"]
        base = "/platform-publications/{platform_publication_id}"
        self.assertIn(f"{base}/metric-snapshots", paths)
        self.assertIn("post", paths[f"{base}/metric-snapshots"])
        self.assertIn("get", paths[f"{base}/metric-snapshots"])
        self.assertIn(f"{base}/growth-summary", paths)


if __name__ == "__main__":
    unittest.main()
