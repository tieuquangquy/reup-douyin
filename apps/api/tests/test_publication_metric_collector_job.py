from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.analytics.collectors.base import MetricCollector, MetricCollectorError
from src.analytics.collectors.local_mock import LocalMockMetricCollector
from src.analytics.collectors.registry import MetricCollectorRegistry
from src.analytics.services.publication_metric_collection_service import (
    METRICS_COOLDOWN_METADATA_KEY,
    PublicationMetricCollectionError,
    PublicationMetricCollectionService,
)
from src.enums import (
    ExternalPublicationStatus,
    JobStatus,
    JobType,
    PlatformAccountStatus,
)
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication
from src.schemas.analytics import (
    PublicationMetricCollectionEnqueueRequest,
    PublicationMetricMockPayload,
)
from src.services.job_runner import resolve_failure_outcome
from src.services.job_templates import get_step_templates


def _request(**overrides) -> PublicationMetricCollectionEnqueueRequest:
    values = {
        "collection_key": "slot-2026-07-28T10:00Z",
        "collector": "LOCAL_MOCK",
        "mock_metrics": PublicationMetricMockPayload(
            observed_at=datetime(2026, 7, 28, 10, 0, tzinfo=UTC),
            view_count=2500,
            like_count=220,
            comment_count=24,
            share_count=15,
            save_count=9,
        ),
    }
    values.update(overrides)
    return PublicationMetricCollectionEnqueueRequest(**values)


class _ReadSession:
    def __init__(self, *, publication, account, job=None, snapshot=None):
        self.publication = publication
        self.account = account
        self.job = job
        self.snapshot = snapshot
        self.commit_count = 0
        self.rollback_count = 0

    def get(self, model, object_id):
        if model is PlatformPublication and object_id == self.publication.id:
            return self.publication
        if model is PlatformAccount and object_id == self.account.id:
            return self.account
        if model is Job and self.job is not None and object_id == self.job.id:
            return self.job
        return None

    def scalar(self, statement):
        sql = str(statement)
        if "FROM jobs" in sql:
            return self.job
        if "FROM publication_metric_snapshots" in sql:
            return self.snapshot
        return None

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class _FailIfCalledCollector(MetricCollector):
    def collect(self, **_kwargs):
        raise AssertionError("collector must not be called after the snapshot was persisted")


class _RateLimitedCollector(MetricCollector):
    def collect(self, **_kwargs):
        raise MetricCollectorError(
            "metrics_rate_limited",
            "Provider quota exhausted",
            retryable=True,
            retry_after_seconds=300,
        )


class _UnexpectedCollector(MetricCollector):
    def collect(self, **_kwargs):
        raise RuntimeError("provider implementation failed")


class PublicationMetricCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.account = SimpleNamespace(
            id=uuid4(),
            status=PlatformAccountStatus.ACTIVE,
            is_on_hold=False,
            cooldown_until=None,
            metadata_json={},
        )
        self.publication = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            platform_account_id=self.account.id,
            external_publish_id="local-post-1",
            status=ExternalPublicationStatus.PUBLISHED,
        )

    def test_job_template_has_one_external_collection_boundary(self) -> None:
        keys = [step.key for step in get_step_templates(JobType.COLLECT_PUBLICATION_METRICS)]
        self.assertEqual(
            keys,
            [
                "validate_publication",
                "validate_account",
                "collect_and_persist_snapshot",
                "finalize",
            ],
        )

    def test_local_mock_collector_is_explicitly_network_free(self) -> None:
        result = LocalMockMetricCollector().collect(
            platform_publication_id=self.publication.id,
            platform_account_id=self.account.id,
            external_publish_id=self.publication.external_publish_id,
            payload={"mock_metrics": _request().mock_metrics.model_dump(mode="json")},
        )
        self.assertEqual(result.view_count, 2500)
        self.assertEqual(result.provider_summary["provider"], "LOCAL_MOCK")
        self.assertFalse(result.provider_summary["network_used"])

    def test_enqueue_retry_returns_existing_job_for_same_payload(self) -> None:
        request = _request()
        from src.analytics.services.publication_metrics_helpers import canonical_payload_hash

        job = SimpleNamespace(
            id=uuid4(),
            payload_json={
                "request_hash_sha256": canonical_payload_hash(request.model_dump(mode="json"))
            },
        )
        session = _ReadSession(
            publication=self.publication,
            account=self.account,
            job=job,
        )
        service = PublicationMetricCollectionService(session)  # type: ignore[arg-type]

        result = service.enqueue(self.publication.id, request)

        self.assertIs(result, job)

    def test_enqueue_same_key_with_changed_payload_fails_closed(self) -> None:
        job = SimpleNamespace(id=uuid4(), payload_json={"request_hash_sha256": "0" * 64})
        session = _ReadSession(
            publication=self.publication,
            account=self.account,
            job=job,
        )
        service = PublicationMetricCollectionService(session)  # type: ignore[arg-type]

        with self.assertRaises(PublicationMetricCollectionError) as context:
            service.enqueue(self.publication.id, _request())

        self.assertEqual(context.exception.code, "metrics_collection_idempotency_conflict")

    def test_local_mock_is_blocked_in_production(self) -> None:
        session = _ReadSession(
            publication=self.publication,
            account=self.account,
            job=None,
        )
        service = PublicationMetricCollectionService(session)  # type: ignore[arg-type]

        with (
            patch(
                "src.analytics.services.publication_metric_collection_service.get_settings",
                return_value=SimpleNamespace(app_env="production"),
            ),
            self.assertRaises(PublicationMetricCollectionError) as context,
        ):
            service.enqueue(self.publication.id, _request())

        self.assertEqual(context.exception.code, "metrics_mock_disabled_in_production")

    def test_resume_uses_existing_snapshot_without_provider_call(self) -> None:
        self.account.is_on_hold = True
        self.account.cooldown_until = datetime.now(UTC) + timedelta(hours=1)
        job = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            payload_json={"platform_publication_id": str(self.publication.id)},
            result_json=None,
            metadata_json={},
        )
        snapshot = SimpleNamespace(
            id=uuid4(),
            platform_publication_id=self.publication.id,
            observed_at=datetime(2026, 7, 28, 10, 0, tzinfo=UTC),
        )
        session = _ReadSession(
            publication=self.publication,
            account=self.account,
            job=job,
            snapshot=snapshot,
        )
        registry = MetricCollectorRegistry({"LOCAL_MOCK": _FailIfCalledCollector()})
        service = PublicationMetricCollectionService(session, registry=registry)  # type: ignore[arg-type]

        result = service.execute_job(job.id)

        self.assertIs(result, snapshot)
        self.assertTrue(job.result_json["resumed_from_existing_snapshot"])
        self.assertEqual(session.commit_count, 1)

    def test_rate_limit_sets_metrics_only_cooldown(self) -> None:
        job = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            payload_json={
                "platform_publication_id": str(self.publication.id),
                "collector": "RATE_LIMIT_TEST",
            },
            result_json=None,
            metadata_json={},
        )
        session = _ReadSession(
            publication=self.publication,
            account=self.account,
            job=job,
            snapshot=None,
        )
        registry = MetricCollectorRegistry({"RATE_LIMIT_TEST": _RateLimitedCollector()})
        service = PublicationMetricCollectionService(session, registry=registry)  # type: ignore[arg-type]

        with self.assertRaises(PublicationMetricCollectionError) as context:
            service.execute_job(job.id)

        self.assertEqual(context.exception.code, "metrics_rate_limited")
        self.assertEqual(context.exception.retry_after_seconds, 300)
        self.assertIn(METRICS_COOLDOWN_METADATA_KEY, self.account.metadata_json)
        self.assertIsNone(self.account.cooldown_until)
        self.assertEqual(session.commit_count, 1)

    def test_unexpected_collector_error_becomes_safe_retryable_job_error(self) -> None:
        job = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            payload_json={
                "platform_publication_id": str(self.publication.id),
                "collector": "UNEXPECTED_TEST",
            },
            result_json=None,
            metadata_json={},
        )
        session = _ReadSession(
            publication=self.publication,
            account=self.account,
            job=job,
            snapshot=None,
        )
        registry = MetricCollectorRegistry({"UNEXPECTED_TEST": _UnexpectedCollector()})
        service = PublicationMetricCollectionService(session, registry=registry)  # type: ignore[arg-type]

        with self.assertRaises(PublicationMetricCollectionError) as context:
            service.execute_job(job.id)

        self.assertEqual(context.exception.code, "metrics_unhandled_error")
        self.assertTrue(context.exception.retryable)
        self.assertNotIn("provider implementation failed", str(context.exception))
        self.assertEqual(session.rollback_count, 1)

    def test_rate_limit_policy_uses_retry_after_and_terminal_stops(self) -> None:
        now = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)
        rate_limited = resolve_failure_outcome(
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            attempts=1,
            retryable=True,
            max_attempts=5,
            error_code="metrics_rate_limited",
            error_message="Provider quota exhausted",
            retry_after_seconds=300,
            now=now,
        )
        terminal = resolve_failure_outcome(
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            attempts=1,
            retryable=True,
            max_attempts=5,
            error_code="metrics_account_on_hold",
            error_message="Account held",
            now=now,
        )

        self.assertEqual(rate_limited.status, JobStatus.RETRYABLE)
        self.assertEqual(rate_limited.scheduled_at, now + timedelta(seconds=300))
        self.assertEqual(terminal.status, JobStatus.FAILED)
        self.assertIsNone(terminal.scheduled_at)

        long_cooldown = resolve_failure_outcome(
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            attempts=1,
            retryable=True,
            max_attempts=5,
            error_code="metrics_account_cooldown",
            error_message="Account cooldown active",
            retry_after_seconds=7200,
            now=now,
        )
        self.assertEqual(long_cooldown.scheduled_at, now + timedelta(seconds=7200))

    def test_collection_route_is_registered(self) -> None:
        from src.main import app

        path = "/platform-publications/{platform_publication_id}/metric-collection-jobs"
        self.assertIn(path, app.openapi()["paths"])
        self.assertIn("post", app.openapi()["paths"][path])


if __name__ == "__main__":
    unittest.main()
