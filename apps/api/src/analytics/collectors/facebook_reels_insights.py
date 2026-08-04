from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

from src.analytics.collectors.base import MetricCollectionResult, MetricCollector, MetricCollectorError
from src.publish.types import PlatformAccountConfig


DEFAULT_FACEBOOK_VIDEO_INSIGHT_METRICS = (
    "total_video_views",
    "post_video_view_time",
    "total_video_complete_views",
)
ALLOWED_FACEBOOK_VIDEO_INSIGHT_METRICS = frozenset(
    {
        *DEFAULT_FACEBOOK_VIDEO_INSIGHT_METRICS,
        "post_video_views",
        "post_video_view_time",
        "post_video_complete_views_organic",
        "total_video_impressions",
        "post_video_impressions",
        "total_video_reactions_by_type_total",
        "like_count",
        "comment_count",
        "share_count",
        "save_count",
        "reach",
    }
)
RATE_LIMIT_GRAPH_CODES = {4, 17, 32, 613}
AUTH_GRAPH_CODES = {10, 190, 200}


class FacebookInsightsTransport:
    graph_base_url = "https://graph.facebook.com"
    request_timeout_seconds = 60

    def fetch_video_insights(
        self,
        *,
        account: PlatformAccountConfig,
        media_id: str,
        metric_names: list[str],
    ) -> dict:
        graph_api_version = _resolve_graph_api_version(account.graph_api_version)
        url = (
            f"{self.graph_base_url}/{graph_api_version}/{parse.quote(media_id, safe='')}"
            f"/video_insights?{parse.urlencode({'metric': ','.join(metric_names), 'period': 'lifetime'})}"
        )
        return self._fetch_json(
            account=account,
            url=url,
            operation="insights",
        )

    def fetch_video_counters(
        self,
        *,
        account: PlatformAccountConfig,
        media_id: str,
    ) -> dict:
        """Read Reel counters exposed on the video object in modern Graph versions."""
        graph_api_version = _resolve_graph_api_version(account.graph_api_version)
        fields = "id,views,likes.limit(0).summary(true),comments.limit(0).summary(true)"
        url = (
            f"{self.graph_base_url}/{graph_api_version}/{parse.quote(media_id, safe='')}"
            f"?{parse.urlencode({'fields': fields})}"
        )
        return self._fetch_json(
            account=account,
            url=url,
            operation="video counters",
        )

    def _fetch_json(
        self,
        *,
        account: PlatformAccountConfig,
        url: str,
        operation: str,
    ) -> dict:
        req = request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {account.access_token}",
                "Accept": "application/json",
                "User-Agent": "reup-douyin/metrics-v1",
            },
        )
        try:
            with request.urlopen(req, timeout=self.request_timeout_seconds) as response:
                payload_text = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            payload = _parse_payload(body)
            self._raise_graph_error(payload, http_status=exc.code, headers=exc.headers)
            raise MetricCollectorError(
                "metrics_provider_unavailable",
                f"Facebook Graph {operation} HTTP {exc.code}",
                retryable=exc.code >= 500,
                provider_summary=_safe_error_summary(payload, exc.code),
            ) from exc
        except URLError as exc:
            raise MetricCollectorError(
                "metrics_provider_unavailable",
                f"Facebook Graph {operation} request failed: {exc.reason}",
                retryable=True,
            ) from exc

        payload = _parse_payload(payload_text)
        self._raise_graph_error(payload, http_status=200, headers=None)
        return payload

    @staticmethod
    def _raise_graph_error(payload: dict, *, http_status: int, headers: Any) -> None:
        error = payload.get("error") if isinstance(payload, dict) else None
        graph_code = _coerce_int(error.get("code")) if isinstance(error, dict) else None
        retry_after = _retry_after_seconds(headers)
        summary = _safe_error_summary(payload, http_status)
        if http_status == 429 or graph_code in RATE_LIMIT_GRAPH_CODES:
            raise MetricCollectorError(
                "metrics_rate_limited",
                "Facebook insights rate limit reached",
                retryable=True,
                retry_after_seconds=retry_after,
                provider_summary=summary,
            )
        if http_status in {401, 403} or graph_code in AUTH_GRAPH_CODES:
            raise MetricCollectorError(
                "metrics_auth_or_permission_denied",
                "Facebook insights token or permission was rejected",
                retryable=False,
                provider_summary=summary,
            )
        graph_message = str(error.get("message") or "").lower() if isinstance(error, dict) else ""
        missing_object = http_status == 404 or (
            graph_code == 100
            and any(
                marker in graph_message
                for marker in (
                    "unsupported get request",
                    "object with id",
                    "cannot be loaded",
                    "does not exist",
                )
            )
        )
        if missing_object:
            raise MetricCollectorError(
                "metrics_media_not_found",
                "Facebook insights media object was not found",
                retryable=False,
                provider_summary=summary,
            )
        if graph_code == 100:
            raise MetricCollectorError(
                "metrics_provider_request_invalid",
                "Facebook rejected an Insights metric or field parameter",
                retryable=False,
                provider_summary=summary,
            )
        if error:
            raise MetricCollectorError(
                "metrics_provider_unavailable",
                "Facebook insights returned an error",
                retryable=http_status >= 500,
                provider_summary=summary,
            )


class FacebookReelsInsightsCollector(MetricCollector):
    def __init__(self, transport: FacebookInsightsTransport | None = None):
        self.transport = transport or FacebookInsightsTransport()

    def collect(
        self,
        *,
        platform_publication_id,
        platform_account_id,
        external_publish_id: str,
        payload: dict,
        external_media_id: str | None = None,
        external_reel_id: str | None = None,
        account_config: object | None = None,
        collector_config: dict | None = None,
    ) -> MetricCollectionResult:
        if not isinstance(account_config, PlatformAccountConfig):
            raise MetricCollectorError(
                "metrics_account_credentials_missing",
                "Facebook insights account credentials were not resolved in the worker",
                retryable=False,
            )
        config = collector_config or {}
        media_id = _resolve_media_id(
            config.get("facebook_insights_object_id_source"),
            external_publish_id=external_publish_id,
            external_media_id=external_media_id,
            external_reel_id=external_reel_id,
        )
        if not media_id:
            raise MetricCollectorError(
                "metrics_media_reference_missing",
                "Facebook insights requires an external media/reel id",
                retryable=False,
            )
        metric_names = _resolve_metric_names(config.get("facebook_insights_metrics"))
        graph_api_version = _resolve_graph_api_version(account_config.graph_api_version)
        view_time_unit = _resolve_view_time_unit(config.get("facebook_view_time_unit"))
        response = self.transport.fetch_video_insights(
            account=account_config,
            media_id=media_id,
            metric_names=metric_names,
        )
        counters = self.transport.fetch_video_counters(
            account=account_config,
            media_id=media_id,
        )
        normalized = normalize_facebook_video_insights(
            response,
            requested_metrics=metric_names,
            view_time_unit=view_time_unit,
            counter_payload=counters,
        )
        return MetricCollectionResult(
            observed_at=datetime.now(UTC),
            collection_source="PLATFORM_API",
            provider_schema_version=f"facebook-graph-{graph_api_version}",
            view_count=normalized["view_count"],
            like_count=normalized["like_count"],
            comment_count=normalized["comment_count"],
            share_count=normalized["share_count"],
            save_count=normalized["save_count"],
            impression_count=normalized["impression_count"],
            reach_count=normalized["reach_count"],
            total_watch_time_seconds=normalized["total_watch_time_seconds"],
            completion_rate_percent=normalized["completion_rate_percent"],
            data_quality=normalized["data_quality"],
            unavailable_metrics=normalized["unavailable_metrics"],
            provider_summary={
                "provider": "FACEBOOK_GRAPH",
                "graph_api_version": graph_api_version,
                "media_reference_source": normalized["media_reference_source"],
                "requested_metrics": metric_names,
                "returned_metrics": normalized["returned_metrics"],
                "network_used": True,
            },
        )


def normalize_facebook_video_insights(
    payload: dict,
    *,
    requested_metrics: list[str],
    view_time_unit: str = "milliseconds",
    counter_payload: dict | None = None,
) -> dict:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise MetricCollectorError(
            "metrics_provider_payload_invalid",
            "Facebook insights response is missing data[]",
            retryable=False,
        )
    values: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        raw_values = row.get("values")
        raw_value = raw_values[-1].get("value") if isinstance(raw_values, list) and raw_values and isinstance(raw_values[-1], dict) else row.get("value")
        values[str(row["name"])] = raw_value

    counters = normalize_facebook_video_counters(counter_payload or {})
    view_count = counters["view_count"]
    if view_count is None:
        view_count = _first_int(values, "total_video_views", "post_video_views")
    complete_views = _first_int(
        values,
        "total_video_complete_views",
        "post_video_complete_views_organic",
    )
    raw_view_time = _first_float(values, "total_video_view_time", "post_video_view_time")
    if raw_view_time is not None and view_time_unit.lower() == "milliseconds":
        total_watch_time_seconds = raw_view_time / 1000
    else:
        total_watch_time_seconds = raw_view_time
    reactions = values.get("total_video_reactions_by_type_total")
    reaction_like = _coerce_int(reactions.get("like")) if isinstance(reactions, dict) else None
    like_count = counters["like_count"]
    if like_count is None:
        like_count = _first_int(values, "like_count")
    if like_count is None:
        like_count = reaction_like
    completion_rate = (
        round((complete_views / view_count) * 100, 6)
        if complete_views is not None and view_count is not None and view_count > 0
        else None
    )
    returned = sorted(values)
    if counters["view_count"] is not None:
        returned.append("object.views")
    if counters["like_count"] is not None:
        returned.append("object.likes.summary.total_count")
    if counters["comment_count"] is not None:
        returned.append("object.comments.summary.total_count")
    unavailable = [
        name
        for name in requested_metrics
        if name not in values
        and not (name in {"total_video_views", "post_video_views"} and view_count is not None)
        and not (name == "like_count" and like_count is not None)
        and not (name == "comment_count" and counters["comment_count"] is not None)
    ]
    return {
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": counters["comment_count"]
        if counters["comment_count"] is not None
        else _first_int(values, "comment_count"),
        "share_count": _first_int(values, "share_count"),
        "save_count": _first_int(values, "save_count"),
        "impression_count": _first_int(values, "total_video_impressions", "post_video_impressions"),
        "reach_count": _first_int(values, "reach"),
        "total_watch_time_seconds": total_watch_time_seconds,
        "completion_rate_percent": completion_rate,
        "returned_metrics": returned,
        "unavailable_metrics": unavailable,
        "data_quality": "COMPLETE" if not unavailable and view_count is not None else "PARTIAL",
        "media_reference_source": "configured_external_reference",
    }


def normalize_facebook_video_counters(payload: dict) -> dict[str, int | None]:
    def summary_count(name: str) -> int | None:
        container = payload.get(name) if isinstance(payload, dict) else None
        summary = container.get("summary") if isinstance(container, dict) else None
        return _coerce_int(summary.get("total_count")) if isinstance(summary, dict) else None

    return {
        "view_count": _coerce_int(payload.get("views")) if isinstance(payload, dict) else None,
        "like_count": summary_count("likes"),
        "comment_count": summary_count("comments"),
    }


def _resolve_metric_names(raw: Any) -> list[str]:
    requested = list(raw) if isinstance(raw, list) else list(DEFAULT_FACEBOOK_VIDEO_INSIGHT_METRICS)
    normalized = []
    for value in requested:
        name = str(value).strip()
        if name and name in ALLOWED_FACEBOOK_VIDEO_INSIGHT_METRICS and name not in normalized:
            normalized.append(name)
    if not normalized:
        raise MetricCollectorError(
            "metrics_configuration_invalid",
            "No allowlisted Facebook insights metrics were configured",
            retryable=False,
        )
    return normalized


def _resolve_media_id(
    source: Any,
    *,
    external_publish_id: str | None,
    external_media_id: str | None,
    external_reel_id: str | None,
) -> str | None:
    by_source = {
        "external_publish_id": external_publish_id,
        "external_media_id": external_media_id,
        "external_reel_id": external_reel_id,
    }
    if source is not None and source not in by_source:
        raise MetricCollectorError(
            "metrics_configuration_invalid",
            "facebook_insights_object_id_source is not supported",
            retryable=False,
        )
    if source in by_source:
        return by_source[str(source)]
    return external_media_id or external_reel_id or external_publish_id


def _resolve_graph_api_version(raw: Any) -> str:
    version = str(raw or "").strip()
    if not re.fullmatch(r"v\d+\.\d+", version):
        raise MetricCollectorError(
            "metrics_configuration_invalid",
            "Facebook graph_api_version must use the v<major>.<minor> format",
            retryable=False,
        )
    return version


def _resolve_view_time_unit(raw: Any) -> str:
    unit = str(raw or "milliseconds").strip().lower()
    if unit not in {"milliseconds", "seconds"}:
        raise MetricCollectorError(
            "metrics_configuration_invalid",
            "facebook_view_time_unit must be milliseconds or seconds",
            retryable=False,
        )
    return unit


def _parse_payload(text: str) -> dict:
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise MetricCollectorError(
            "metrics_provider_payload_invalid",
            "Facebook insights returned non-JSON data",
            retryable=False,
        ) from exc
    return payload if isinstance(payload, dict) else {}


def _safe_error_summary(payload: dict, http_status: int) -> dict:
    error = payload.get("error") if isinstance(payload, dict) else None
    return {
        "provider": "FACEBOOK_GRAPH",
        "http_status": http_status,
        "graph_error_code": _coerce_int(error.get("code")) if isinstance(error, dict) else None,
        "graph_error_subcode": _coerce_int(error.get("error_subcode")) if isinstance(error, dict) else None,
    }


def _retry_after_seconds(headers: Any) -> int | None:
    if headers is None:
        return None
    try:
        return max(1, int(headers.get("Retry-After"))) if headers.get("Retry-After") else None
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first_int(values: dict[str, Any], *names: str) -> int | None:
    for name in names:
        result = _coerce_int(values.get(name))
        if result is not None:
            return result
    return None


def _first_float(values: dict[str, Any], *names: str) -> float | None:
    for name in names:
        try:
            value = values.get(name)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None
