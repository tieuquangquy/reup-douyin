from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


class MetricCollectorError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        retry_after_seconds: int | None = None,
        provider_summary: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider_summary = provider_summary or {}


@dataclass(frozen=True)
class MetricCollectionResult:
    observed_at: datetime
    collection_source: str
    provider_schema_version: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    save_count: int | None = None
    impression_count: int | None = None
    reach_count: int | None = None
    follower_gain_count: int | None = None
    total_watch_time_seconds: float | None = None
    average_watch_time_seconds: float | None = None
    completion_rate_percent: float | None = None
    is_estimated: bool = False
    data_quality: str = "UNKNOWN"
    unavailable_metrics: list[str] | None = None
    provider_summary: dict = field(default_factory=dict)


class MetricCollector(ABC):
    @abstractmethod
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
        raise NotImplementedError
