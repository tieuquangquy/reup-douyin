"""Run a PostgreSQL Facebook Reels insights pilot without external network access.

The script exercises the durable enqueue -> JobRunner -> snapshot path with a fixture
transport. It temporarily enables the exact account capability and resolves a dummy
token through the normal worker-only environment boundary, then restores both values.
Persisted job/snapshot evidence is retained; no Facebook endpoint can be reached.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select

from src.analytics.collectors.facebook_reels_insights import FacebookReelsInsightsCollector
from src.analytics.collectors.registry import MetricCollectorRegistry
from src.analytics.services.publication_metric_collection_service import (
    PublicationMetricCollectionService,
)
from src.db.session import get_engine, get_session_factory
from src.enums import ExternalPublicationStatus, JobStatus, PublishTargetPlatform
from src.models.analytics import PublicationMetricSnapshot
from src.models.publish import PlatformAccount, PlatformPublication
from src.schemas.analytics import PublicationMetricCollectionEnqueueRequest
from src.services.job_runner import JobRunner


FIXTURE = {
    "data": [
        {"name": "total_video_views", "period": "lifetime", "values": [{"value": 5100}]},
        {
            "name": "total_video_view_time",
            "period": "lifetime",
            "values": [{"value": 663000}],
        },
        {
            "name": "total_video_complete_views",
            "period": "lifetime",
            "values": [{"value": 3315}],
        },
    ]
}


class FixtureTransport:
    """In-memory transport: deliberately has no URL or socket implementation."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch_video_insights(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return deepcopy(FIXTURE)


def _select_publication(db, publication_id: UUID | None) -> PlatformPublication:
    statement = (
        select(PlatformPublication)
        .join(PlatformAccount, PlatformPublication.platform_account_id == PlatformAccount.id)
        .where(
            PlatformPublication.platform == PublishTargetPlatform.FACEBOOK_REELS,
            PlatformPublication.status == ExternalPublicationStatus.PUBLISHED,
        )
        .order_by(PlatformPublication.created_at.desc())
    )
    if publication_id is not None:
        statement = statement.where(PlatformPublication.id == publication_id)
    publication = db.scalar(statement.limit(1))
    if publication is None:
        raise RuntimeError("No confirmed Facebook Reels publication is available for the fixture pilot")
    return publication


def _serialized_persistence(job, snapshot: PublicationMetricSnapshot) -> str:
    return json.dumps(
        {
            "job_payload": job.payload_json,
            "job_context": job.context_json,
            "job_result": job.result_json,
            "job_metadata": job.metadata_json,
            "snapshot_provider_summary": snapshot.provider_summary_json,
            "snapshot_metadata": snapshot.metadata_json,
            "snapshot_unavailable": snapshot.unavailable_metrics_json,
        },
        default=str,
        sort_keys=True,
    )


def run(publication_id: UUID | None = None) -> dict:
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("The fixture pilot requires PostgreSQL persistence")

    db = get_session_factory()()
    account: PlatformAccount | None = None
    original_metadata: dict | None = None
    token_reference: str | None = None
    previous_env_token: str | None = None
    dummy_token = f"fixture-only-{uuid4().hex}"
    try:
        publication = _select_publication(db, publication_id)
        account = db.get(PlatformAccount, publication.platform_account_id)
        if account is None:
            raise RuntimeError("Pilot publication account does not exist")
        if not str(account.external_account_id or "").strip():
            raise RuntimeError("Pilot account requires an explicit external_account_id")
        token_reference = str(account.token_reference or "").strip()
        if not token_reference:
            raise RuntimeError("Pilot account requires an explicit token_reference")

        original_metadata = deepcopy(account.metadata_json)
        account.metadata_json = {
            **(account.metadata_json or {}),
            "metrics_insights_enabled": True,
            "facebook_insights_object_id_source": "external_reel_id",
            "facebook_insights_metrics": [
                "total_video_views",
                "total_video_view_time",
                "total_video_complete_views",
            ],
            "facebook_view_time_unit": "milliseconds",
        }
        db.commit()

        previous_env_token = os.environ.get(token_reference)
        os.environ[token_reference] = dummy_token

        transport = FixtureTransport()
        registry = MetricCollectorRegistry(
            {"FACEBOOK_GRAPH": FacebookReelsInsightsCollector(transport=transport)}  # type: ignore[arg-type]
        )
        collection_service = PublicationMetricCollectionService(
            db,
            registry=registry,
            enforce_facebook_live_preflight=False,
        )
        job = collection_service.enqueue(
            publication.id,
            PublicationMetricCollectionEnqueueRequest(
                collection_key=f"facebook-fixture-pilot:{uuid4().hex}",
                collector="FACEBOOK_GRAPH",
                external_network_authorized=True,
            ),
        )

        with patch(
            "src.analytics.services.publication_metric_collection_service.PublicationMetricCollectionService",
            return_value=collection_service,
        ):
            completed_job = JobRunner(db).run_job(job.id)

        if completed_job.status != JobStatus.COMPLETED:
            raise RuntimeError(
                f"Fixture pilot job did not complete: {completed_job.status} / {completed_job.error_code}"
            )
        snapshot = db.scalar(
            select(PublicationMetricSnapshot).where(
                PublicationMetricSnapshot.platform_publication_id == publication.id,
                PublicationMetricSnapshot.idempotency_key == f"metric-collection-job:{job.id}",
            )
        )
        if snapshot is None:
            raise RuntimeError("Fixture pilot completed without a metric snapshot")

        resumed = collection_service.execute_job(job.id)
        if resumed.id != snapshot.id:
            raise RuntimeError("Resume returned a different metric snapshot")
        if len(transport.calls) != 1:
            raise RuntimeError(f"Fixture provider call count must be 1, got {len(transport.calls)}")
        persisted = _serialized_persistence(completed_job, snapshot)
        if dummy_token in persisted:
            raise RuntimeError("Dummy access token leaked into persisted job/snapshot state")

        return {
            "network_used": False,
            "publication_id": str(publication.id),
            "platform_account_id": str(account.id),
            "job_id": str(job.id),
            "job_status": completed_job.status.value,
            "snapshot_id": str(snapshot.id),
            "provider_call_count": len(transport.calls),
            "resume_reused_snapshot": True,
            "token_persisted": False,
            "view_count": snapshot.view_count,
            "total_watch_time_seconds": snapshot.total_watch_time_seconds,
            "completion_rate_percent": snapshot.completion_rate_percent,
            "data_quality": snapshot.data_quality,
        }
    finally:
        if token_reference:
            if previous_env_token is None:
                os.environ.pop(token_reference, None)
            else:
                os.environ[token_reference] = previous_env_token
        if account is not None:
            account.metadata_json = original_metadata
            db.commit()
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-id", type=UUID)
    args = parser.parse_args()
    print(json.dumps(run(args.publication_id), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
