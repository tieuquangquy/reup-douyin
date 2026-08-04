from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from src.analytics.collectors.base import MetricCollectionResult, MetricCollector, MetricCollectorError


class LocalMockMetricCollector(MetricCollector):
    """Deterministic local collector used for contract tests without external I/O."""

    def collect(
        self,
        *,
        platform_publication_id: UUID,
        platform_account_id: UUID,
        external_publish_id: str,
        payload: dict,
        external_media_id: str | None = None,
        external_reel_id: str | None = None,
        account_config: object | None = None,
        collector_config: dict | None = None,
    ) -> MetricCollectionResult:
        metrics = payload.get("mock_metrics")
        if not isinstance(metrics, dict):
            raise MetricCollectorError(
                "metrics_mock_payload_missing",
                "LOCAL_MOCK requires mock_metrics",
                retryable=False,
            )
        observed_raw = metrics.get("observed_at")
        if observed_raw:
            try:
                observed_at = datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
            except ValueError as exc:
                raise MetricCollectorError(
                    "metrics_mock_observed_at_invalid",
                    "LOCAL_MOCK observed_at is invalid",
                    retryable=False,
                ) from exc
        else:
            observed_at = datetime.now(UTC)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise MetricCollectorError(
                "metrics_mock_observed_at_invalid",
                "LOCAL_MOCK observed_at must include a timezone",
                retryable=False,
            )

        return MetricCollectionResult(
            observed_at=observed_at,
            collection_source="LOCAL_MOCK",
            provider_schema_version="local-mock-v1",
            view_count=metrics.get("view_count"),
            like_count=metrics.get("like_count"),
            comment_count=metrics.get("comment_count"),
            share_count=metrics.get("share_count"),
            save_count=metrics.get("save_count"),
            impression_count=metrics.get("impression_count"),
            reach_count=metrics.get("reach_count"),
            follower_gain_count=metrics.get("follower_gain_count"),
            total_watch_time_seconds=metrics.get("total_watch_time_seconds"),
            average_watch_time_seconds=metrics.get("average_watch_time_seconds"),
            completion_rate_percent=metrics.get("completion_rate_percent"),
            is_estimated=bool(metrics.get("is_estimated", False)),
            data_quality=str(metrics.get("data_quality") or "COMPLETE"),
            unavailable_metrics=metrics.get("unavailable_metrics"),
            provider_summary={
                "provider": "LOCAL_MOCK",
                "external_publish_id": external_publish_id,
                "network_used": False,
            },
        )
