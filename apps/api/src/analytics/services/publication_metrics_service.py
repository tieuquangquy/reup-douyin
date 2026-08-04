from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.analytics.services.publication_metrics_helpers import (
    build_growth_summary,
    canonical_payload_hash,
    contains_sensitive_key,
    recompute_snapshot_series,
)
from src.models.analytics import PublicationMetricSnapshot
from src.models.publish import PlatformPublication
from src.schemas.analytics import PublicationMetricSnapshotCreateRequest

logger = logging.getLogger(__name__)


class PublicationMetricsError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PublicationMetricsService:
    def __init__(self, db: Session):
        self.db = db

    def record_snapshot(
        self,
        platform_publication_id: UUID,
        request: PublicationMetricSnapshotCreateRequest,
    ) -> PublicationMetricSnapshot:
        publication = self._get_publication(platform_publication_id)
        self._reject_sensitive_summaries(request)
        payload_hash = self._request_payload_hash(request)
        existing = self._find_by_idempotency_key(platform_publication_id, request.idempotency_key)
        if existing is not None:
            self._assert_same_payload(existing, payload_hash)
            return existing

        snapshot = PublicationMetricSnapshot(
            workspace_id=publication.workspace_id,
            platform_publication_id=publication.id,
            observed_at=request.observed_at,
            collection_source=request.collection_source,
            provider_schema_version=request.provider_schema_version,
            idempotency_key=request.idempotency_key,
            payload_hash_sha256=payload_hash,
            view_count=request.view_count,
            like_count=request.like_count,
            comment_count=request.comment_count,
            share_count=request.share_count,
            save_count=request.save_count,
            impression_count=request.impression_count,
            reach_count=request.reach_count,
            follower_gain_count=request.follower_gain_count,
            total_watch_time_seconds=request.total_watch_time_seconds,
            average_watch_time_seconds=request.average_watch_time_seconds,
            completion_rate_percent=request.completion_rate_percent,
            is_estimated=request.is_estimated,
            data_quality=request.data_quality,
            unavailable_metrics_json=request.unavailable_metrics,
            provider_summary_json=request.provider_summary_json,
            metadata_json=request.metadata_json,
        )
        self.db.add(snapshot)
        try:
            self.db.flush()
            recompute_snapshot_series(self._all_snapshots(platform_publication_id))
            self.db.commit()
            self.db.refresh(snapshot)
        except IntegrityError as exc:
            self.db.rollback()
            concurrent = self._find_by_idempotency_key(platform_publication_id, request.idempotency_key)
            if concurrent is None:
                raise
            self._assert_same_payload(concurrent, payload_hash)
            return concurrent

        logger.info(
            "publication_metric_snapshot_recorded",
            extra={
                "platform_publication_id": str(platform_publication_id),
                "metric_snapshot_id": str(snapshot.id),
                "collection_source": snapshot.collection_source,
            },
        )
        return snapshot

    def list_snapshots(
        self,
        platform_publication_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[PublicationMetricSnapshot], int]:
        self._get_publication(platform_publication_id)
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(PublicationMetricSnapshot)
                .where(PublicationMetricSnapshot.platform_publication_id == platform_publication_id)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(PublicationMetricSnapshot)
                .where(PublicationMetricSnapshot.platform_publication_id == platform_publication_id)
                .order_by(
                    PublicationMetricSnapshot.observed_at.asc(),
                    PublicationMetricSnapshot.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total

    def growth_summary(self, platform_publication_id: UUID) -> dict:
        self._get_publication(platform_publication_id)
        return build_growth_summary(
            platform_publication_id,
            self._all_snapshots(platform_publication_id),
        )

    def _get_publication(self, platform_publication_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, platform_publication_id)
        if publication is None:
            raise PublicationMetricsError("publication_not_found", "Platform publication not found")
        return publication

    def _find_by_idempotency_key(
        self,
        platform_publication_id: UUID,
        idempotency_key: str,
    ) -> PublicationMetricSnapshot | None:
        return self.db.scalar(
            select(PublicationMetricSnapshot)
            .where(
                PublicationMetricSnapshot.platform_publication_id == platform_publication_id,
                PublicationMetricSnapshot.idempotency_key == idempotency_key,
            )
            .limit(1)
        )

    def _all_snapshots(self, platform_publication_id: UUID) -> list[PublicationMetricSnapshot]:
        return list(
            self.db.scalars(
                select(PublicationMetricSnapshot)
                .where(PublicationMetricSnapshot.platform_publication_id == platform_publication_id)
                .order_by(
                    PublicationMetricSnapshot.observed_at.asc(),
                    PublicationMetricSnapshot.id.asc(),
                )
            )
        )

    @staticmethod
    def _request_payload_hash(request: PublicationMetricSnapshotCreateRequest) -> str:
        payload = request.model_dump(mode="json", exclude={"idempotency_key"})
        return canonical_payload_hash(payload)

    @staticmethod
    def _assert_same_payload(existing: PublicationMetricSnapshot, payload_hash: str) -> None:
        if existing.payload_hash_sha256 != payload_hash:
            raise PublicationMetricsError(
                "metric_snapshot_idempotency_conflict",
                "Idempotency key was already used with a different metric payload",
            )

    @staticmethod
    def _reject_sensitive_summaries(request: PublicationMetricSnapshotCreateRequest) -> None:
        if contains_sensitive_key(request.provider_summary_json) or contains_sensitive_key(request.metadata_json):
            raise PublicationMetricsError(
                "sensitive_metric_summary_rejected",
                "Metric summaries must not contain tokens, credentials, cookies, or secrets",
            )
