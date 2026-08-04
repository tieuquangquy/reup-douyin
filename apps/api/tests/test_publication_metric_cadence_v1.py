from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from uuid import uuid4

from pydantic import ValidationError

from src.analytics.services.publication_metric_cadence_policy import decide_next_collection
from src.analytics.services.publication_metric_cadence_service import PublicationMetricCadenceService
from src.models.analytics import PublicationMetricSchedule
from src.models.publish import PlatformPublication
from src.schemas.analytics import PublicationMetricScheduleUpsertRequest


class PublicationMetricCadencePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.published_at = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)

    def test_growing_video_gets_half_interval_with_30_minute_floor(self) -> None:
        decision = decide_next_collection(
            reference_at=self.published_at + timedelta(hours=2),
            published_at=self.published_at,
            trend_label="GROWING",
            consecutive_flat_count=0,
            max_age_hours=168,
        )
        self.assertEqual(decision.interval_seconds, 1800)
        self.assertIn("growing_priority", decision.reason)

    def test_baseline_followup_uses_velocity_minimum_interval(self) -> None:
        decision = decide_next_collection(
            reference_at=self.published_at + timedelta(minutes=1),
            published_at=self.published_at,
            trend_label="BASELINE_ONLY",
            consecutive_flat_count=0,
            max_age_hours=168,
        )
        self.assertEqual(decision.interval_seconds, 30 * 60)
        self.assertIn("baseline_followup", decision.reason)

    def test_repeated_flat_video_backs_off(self) -> None:
        reference = self.published_at + timedelta(hours=10)
        decision = decide_next_collection(
            reference_at=reference,
            published_at=self.published_at,
            trend_label="FLAT",
            consecutive_flat_count=2,
            max_age_hours=168,
        )
        self.assertEqual(decision.interval_seconds, 12 * 3600)
        self.assertEqual(decision.next_collection_at, reference + timedelta(hours=12))

    def test_counter_regression_rechecks_without_using_long_age_band(self) -> None:
        decision = decide_next_collection(
            reference_at=self.published_at + timedelta(hours=30),
            published_at=self.published_at,
            trend_label="COUNTER_REGRESSION",
            consecutive_flat_count=0,
            max_age_hours=168,
        )
        self.assertEqual(decision.interval_seconds, 3 * 3600)

    def test_schedule_completes_at_age_limit(self) -> None:
        decision = decide_next_collection(
            reference_at=self.published_at + timedelta(hours=168),
            published_at=self.published_at,
            trend_label="GROWING",
            consecutive_flat_count=0,
            max_age_hours=168,
        )
        self.assertEqual(decision.status, "COMPLETED")
        self.assertIsNone(decision.next_collection_at)


class _SyncSession:
    def __init__(self, schedule, publication):
        self.schedule = schedule
        self.publication = publication
        self.commit_count = 0

    def get(self, model, object_id):
        if model is PublicationMetricSchedule and object_id == self.schedule.id:
            return self.schedule
        if model is PlatformPublication and object_id == self.publication.id:
            return self.publication
        return None

    def commit(self):
        self.commit_count += 1


class PublicationMetricCadenceSyncTests(unittest.TestCase):
    def test_tracking_health_classifies_waiting_delayed_and_cooldown(self) -> None:
        now = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        schedule = SimpleNamespace(
            status="ACTIVE",
            next_collection_at=now + timedelta(minutes=10),
            last_completed_at=None,
        )
        account = SimpleNamespace(cooldown_until=None, metadata_json={})

        self.assertEqual(
            PublicationMetricCadenceService._classify_tracking_health(
                schedule,
                account,
                None,
                now=now,
            ),
            ("WAITING", "awaiting_first_collection"),
        )

        queued_job = SimpleNamespace(
            status="QUEUED",
            created_at=now - timedelta(minutes=3),
            locked_at=None,
        )
        self.assertEqual(
            PublicationMetricCadenceService._classify_tracking_health(
                schedule,
                account,
                queued_job,
                now=now,
            )[0],
            "DELAYED",
        )

        account.cooldown_until = now + timedelta(minutes=15)
        self.assertEqual(
            PublicationMetricCadenceService._classify_tracking_health(
                schedule,
                account,
                queued_job,
                now=now,
            ),
            ("COOLDOWN", "account_metrics_cooldown"),
        )

    def test_tracking_health_prioritizes_terminal_schedule_states(self) -> None:
        now = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        account = SimpleNamespace(
            cooldown_until=now + timedelta(minutes=10),
            metadata_json={},
        )
        for status, expected in (
            ("BLOCKED", "BLOCKED"),
            ("PAUSED", "PAUSED"),
            ("COMPLETED", "COMPLETED"),
        ):
            schedule = SimpleNamespace(status=status)
            health, _reason = PublicationMetricCadenceService._classify_tracking_health(
                schedule,
                account,
                None,
                now=now,
            )
            self.assertEqual(health, expected)

    def test_facebook_schedule_requires_explicit_recurring_read_authorization(self) -> None:
        with self.assertRaises(ValidationError):
            PublicationMetricScheduleUpsertRequest(
                collector="FACEBOOK_GRAPH",
                external_network_authorized=True,
            )

        request = PublicationMetricScheduleUpsertRequest(
            collector="FACEBOOK_GRAPH",
            external_network_authorized=True,
            operator_confirmation="FACEBOOK_INSIGHTS_AUTO_TRACKING_APPROVED",
            max_age_hours=72,
        )
        self.assertEqual(request.max_age_hours, 72)

    def test_default_start_waits_for_existing_baseline_minimum_interval(self) -> None:
        now = datetime(2026, 7, 28, 8, 5, tzinfo=UTC)
        next_stable = datetime(2026, 7, 28, 8, 30, tzinfo=UTC)
        service = PublicationMetricCadenceService(SimpleNamespace())  # type: ignore[arg-type]
        service.metrics = SimpleNamespace(
            growth_summary=lambda _publication_id: {
                "next_stable_measurement_at": next_stable,
            }
        )
        publication = SimpleNamespace(id=uuid4())

        self.assertEqual(service._default_start_at(publication, now=now), next_stable)

    def test_tracking_horizon_starts_at_operator_activation_not_old_publish_date(self) -> None:
        activated_at = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        schedule = SimpleNamespace(
            metadata_json={"tracking_started_at": activated_at.isoformat()}
        )
        publication = SimpleNamespace(
            published_at=activated_at - timedelta(days=30),
            created_at=activated_at - timedelta(days=30),
        )

        self.assertEqual(
            PublicationMetricCadenceService._tracking_reference_at(schedule, publication),
            activated_at,
        )

    def test_resume_sync_is_idempotent_for_flat_counter(self) -> None:
        published_at = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        schedule = SimpleNamespace(
            id=uuid4(),
            status="ACTIVE",
            platform_publication_id=uuid4(),
            last_metric_snapshot_id=None,
            last_collection_job_id=None,
            last_completed_at=None,
            collection_count=0,
            consecutive_flat_count=0,
            max_age_hours=168,
            next_collection_at=None,
            last_decision_json=None,
            metadata_json={},
        )
        publication = SimpleNamespace(
            id=schedule.platform_publication_id,
            published_at=published_at,
            created_at=published_at,
        )
        job = SimpleNamespace(id=uuid4(), payload_json={"metric_schedule_id": str(schedule.id)})
        snapshot = SimpleNamespace(
            id=uuid4(),
            observed_at=published_at + timedelta(hours=2),
            delta_view_count=0,
        )
        db = _SyncSession(schedule, publication)
        service = PublicationMetricCadenceService(db)  # type: ignore[arg-type]
        service.metrics = SimpleNamespace(
            growth_summary=lambda _publication_id: {"trend_label": "FLAT"}
        )

        service.sync_after_collection(job, snapshot)
        first_next = schedule.next_collection_at
        first_history_size = len(schedule.metadata_json.get("decision_history") or [])
        service.sync_after_collection(job, snapshot)

        self.assertEqual(schedule.collection_count, 1)
        self.assertEqual(schedule.consecutive_flat_count, 1)
        self.assertEqual(schedule.next_collection_at, first_next)
        self.assertEqual(
            len(schedule.metadata_json.get("decision_history") or []),
            first_history_size,
        )

    def test_paused_schedule_records_snapshot_without_reactivating(self) -> None:
        published_at = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
        schedule = SimpleNamespace(
            id=uuid4(),
            status="PAUSED",
            platform_publication_id=uuid4(),
            last_metric_snapshot_id=None,
            last_collection_job_id=None,
            last_completed_at=None,
            collection_count=0,
            consecutive_flat_count=0,
            max_age_hours=168,
            next_collection_at=None,
            last_decision_json={"reason": "operator_paused"},
            metadata_json={},
        )
        publication = SimpleNamespace(
            id=schedule.platform_publication_id,
            published_at=published_at,
            created_at=published_at,
        )
        snapshot = SimpleNamespace(
            id=uuid4(),
            observed_at=published_at + timedelta(hours=2),
            delta_view_count=100,
        )
        job = SimpleNamespace(id=uuid4(), payload_json={"metric_schedule_id": str(schedule.id)})
        service = PublicationMetricCadenceService(_SyncSession(schedule, publication))  # type: ignore[arg-type]

        service.sync_after_collection(job, snapshot)

        self.assertEqual(schedule.status, "PAUSED")
        self.assertIsNone(schedule.next_collection_at)
        self.assertEqual(schedule.collection_count, 1)

    def test_pause_preserves_previous_adaptive_decision_in_bounded_history(self) -> None:
        schedule = SimpleNamespace(
            metadata_json={},
            last_decision_json={"reason": "first_6h:growing_priority"},
        )
        PublicationMetricCadenceService._record_decision(
            schedule,
            {"reason": "operator_paused", "status": "PAUSED"},
        )
        self.assertEqual(schedule.last_decision_json["reason"], "operator_paused")
        self.assertEqual(
            schedule.metadata_json["decision_history"][-1]["reason"],
            "first_6h:growing_priority",
        )


class PublicationMetricCadenceOpenApiTests(unittest.TestCase):
    def test_schedule_routes_are_registered(self) -> None:
        from src.main import app

        paths = app.openapi()["paths"]
        self.assertIn(
            "/platform-publications/{platform_publication_id}/metric-schedule",
            paths,
        )
        self.assertIn("/analytics/metric-schedules/dispatch-due", paths)
        self.assertIn("/analytics/metric-tracking-monitor", paths)
        self.assertIn("/publication-metric-schedules/{schedule_id}/pause", paths)
        self.assertIn("/publication-metric-schedules/{schedule_id}/resume", paths)


if __name__ == "__main__":
    unittest.main()
