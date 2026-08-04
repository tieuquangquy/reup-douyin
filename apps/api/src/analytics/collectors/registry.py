from __future__ import annotations

from src.analytics.collectors.base import MetricCollector, MetricCollectorError
from src.analytics.collectors.local_mock import LocalMockMetricCollector
from src.analytics.collectors.facebook_reels_insights import FacebookReelsInsightsCollector


class MetricCollectorRegistry:
    def __init__(self, collectors: dict[str, MetricCollector] | None = None):
        self._collectors = collectors or {
            "LOCAL_MOCK": LocalMockMetricCollector(),
            "FACEBOOK_GRAPH": FacebookReelsInsightsCollector(),
        }

    def get(self, collector_name: str) -> MetricCollector:
        collector = self._collectors.get(str(collector_name).upper())
        if collector is None:
            raise MetricCollectorError(
                "metrics_collector_not_supported",
                f"Metric collector is not supported: {collector_name}",
                retryable=False,
            )
        return collector
