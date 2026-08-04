from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any, Iterable


COUNT_METRIC_FIELDS = (
    "view_count",
    "like_count",
    "comment_count",
    "share_count",
    "save_count",
)
ENGAGEMENT_METRIC_FIELDS = (
    "like_count",
    "comment_count",
    "share_count",
    "save_count",
)
SENSITIVE_KEY_FRAGMENTS = ("access_token", "authorization", "cookie", "password", "secret")
DERIVATION_VERSION = "PUBLICATION_METRICS_V2"
MIN_STABLE_VELOCITY_INTERVAL_SECONDS = 30 * 60


def _stable_velocity_anchor(rows: list[Any], current: Any) -> Any | None:
    """Newest prior snapshot that still gives a statistically useful time span."""
    for candidate in reversed(rows):
        interval = int((current.observed_at - candidate.observed_at).total_seconds())
        if interval >= MIN_STABLE_VELOCITY_INTERVAL_SECONDS:
            return candidate
    return None


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS):
                return True
            if contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(contains_sensitive_key(item) for item in value)
    return False


def recompute_snapshot_series(rows: Iterable[Any]) -> list[Any]:
    ordered = sorted(rows, key=lambda row: (row.observed_at, str(row.id)))
    previous = None
    prior_rows: list[Any] = []
    for row in ordered:
        row.derivation_version = DERIVATION_VERSION
        row.counter_regression_detected = False
        row.interval_seconds = None
        row.views_per_hour = None
        row.engagement_delta_rate_percent = None

        views = getattr(row, "view_count", None)
        engagement_total = sum(
            int(value)
            for field in ENGAGEMENT_METRIC_FIELDS
            if (value := getattr(row, field, None)) is not None
        )
        row.engagement_rate_percent = (
            round((engagement_total / views) * 100, 6) if views is not None and views > 0 else None
        )

        for field in COUNT_METRIC_FIELDS:
            setattr(row, f"delta_{field}", None)

        if previous is not None:
            interval_seconds = max(0, int((row.observed_at - previous.observed_at).total_seconds()))
            row.interval_seconds = interval_seconds
            deltas: dict[str, int | None] = {}
            for field in COUNT_METRIC_FIELDS:
                current_value = getattr(row, field, None)
                previous_value = getattr(previous, field, None)
                delta = (
                    int(current_value) - int(previous_value)
                    if current_value is not None and previous_value is not None
                    else None
                )
                deltas[field] = delta
                setattr(row, f"delta_{field}", delta)

            row.counter_regression_detected = any(
                delta is not None and delta < 0 for delta in deltas.values()
            )
            velocity_anchor = _stable_velocity_anchor(prior_rows, row)
            if velocity_anchor is not None:
                velocity_seconds = int(
                    (row.observed_at - velocity_anchor.observed_at).total_seconds()
                )
                velocity_deltas = {
                    field: (
                        int(getattr(row, field)) - int(getattr(velocity_anchor, field))
                        if getattr(row, field, None) is not None
                        and getattr(velocity_anchor, field, None) is not None
                        else None
                    )
                    for field in COUNT_METRIC_FIELDS
                }
                velocity_regression = any(
                    delta is not None and delta < 0 for delta in velocity_deltas.values()
                )
                velocity_views = velocity_deltas.get("view_count")
                if velocity_views is not None and velocity_views >= 0 and not velocity_regression:
                    row.views_per_hour = round(
                        velocity_views * 3600 / velocity_seconds,
                        6,
                    )
            else:
                velocity_deltas = {}
                velocity_views = None
                velocity_regression = False

            if velocity_views is not None and velocity_views > 0 and not velocity_regression:
                known_engagement_delta = sum(
                    delta
                    for field in ENGAGEMENT_METRIC_FIELDS
                    if (delta := velocity_deltas.get(field)) is not None
                )
                row.engagement_delta_rate_percent = round(
                    (known_engagement_delta / velocity_views) * 100,
                    6,
                )
        previous = row
        prior_rows.append(row)
    return ordered


def build_growth_summary(platform_publication_id, rows: Iterable[Any], *, now: datetime | None = None) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row.observed_at, str(row.id)))
    if not ordered:
        return {
            "platform_publication_id": platform_publication_id,
            "snapshot_count": 0,
            "trend_label": "NO_DATA",
            "velocity_status": "NO_DATA",
            "minimum_velocity_interval_seconds": MIN_STABLE_VELOCITY_INTERVAL_SECONDS,
        }

    first = ordered[0]
    latest = ordered[-1]
    current_time = now or datetime.now(UTC)
    observation_seconds = max(0, int((latest.observed_at - first.observed_at).total_seconds()))
    measurement_age_seconds = max(0, int((current_time - latest.observed_at).total_seconds()))

    absolute_growth: dict[str, int | None] = {}
    for field in COUNT_METRIC_FIELDS:
        first_value = getattr(first, field, None)
        latest_value = getattr(latest, field, None)
        absolute_growth[field] = (
            int(latest_value) - int(first_value)
            if first_value is not None and latest_value is not None
            else None
        )

    absolute_views = absolute_growth["view_count"]
    views_per_hour_since_first = (
        round(absolute_views * 3600 / observation_seconds, 6)
        if absolute_views is not None
        and absolute_views >= 0
        and observation_seconds >= MIN_STABLE_VELOCITY_INTERVAL_SECONDS
        else None
    )
    velocity_anchor = _stable_velocity_anchor(ordered[:-1], latest)
    velocity_observation_seconds = (
        int((latest.observed_at - velocity_anchor.observed_at).total_seconds())
        if velocity_anchor is not None
        else None
    )
    velocity_view_growth = (
        int(latest.view_count) - int(velocity_anchor.view_count)
        if velocity_anchor is not None
        and getattr(latest, "view_count", None) is not None
        and getattr(velocity_anchor, "view_count", None) is not None
        else None
    )
    recent_views_per_hour = (
        round(velocity_view_growth * 3600 / velocity_observation_seconds, 6)
        if velocity_view_growth is not None
        and velocity_view_growth >= 0
        and velocity_observation_seconds
        else None
    )
    next_stable_measurement_at = (
        first.observed_at + timedelta(seconds=MIN_STABLE_VELOCITY_INTERVAL_SECONDS)
        if observation_seconds < MIN_STABLE_VELOCITY_INTERVAL_SECONDS
        else None
    )
    if len(ordered) == 1:
        trend_label = "BASELINE_ONLY"
        velocity_status = "BASELINE_ONLY"
    elif bool(getattr(latest, "counter_regression_detected", False)):
        trend_label = "COUNTER_REGRESSION"
        velocity_status = "COUNTER_REGRESSION"
    elif recent_views_per_hour is None:
        trend_label = "INSUFFICIENT_DATA"
        velocity_status = "INSUFFICIENT_INTERVAL"
    elif velocity_view_growth and velocity_view_growth > 0:
        trend_label = "GROWING"
        velocity_status = "STABLE"
    else:
        trend_label = "FLAT"
        velocity_status = "STABLE"

    return {
        "platform_publication_id": platform_publication_id,
        "snapshot_count": len(ordered),
        "first_observed_at": first.observed_at,
        "latest_observed_at": latest.observed_at,
        "observation_hours": round(observation_seconds / 3600, 6),
        "measurement_age_seconds": measurement_age_seconds,
        "trend_label": trend_label,
        "velocity_status": velocity_status,
        "minimum_velocity_interval_seconds": MIN_STABLE_VELOCITY_INTERVAL_SECONDS,
        "velocity_observation_seconds": velocity_observation_seconds,
        "next_stable_measurement_at": next_stable_measurement_at,
        "latest_view_count": getattr(latest, "view_count", None),
        "latest_like_count": getattr(latest, "like_count", None),
        "latest_comment_count": getattr(latest, "comment_count", None),
        "latest_share_count": getattr(latest, "share_count", None),
        "latest_save_count": getattr(latest, "save_count", None),
        "absolute_view_growth": absolute_growth["view_count"],
        "absolute_like_growth": absolute_growth["like_count"],
        "absolute_comment_growth": absolute_growth["comment_count"],
        "absolute_share_growth": absolute_growth["share_count"],
        "absolute_save_growth": absolute_growth["save_count"],
        "views_per_hour_since_first": views_per_hour_since_first,
        "recent_views_per_hour": recent_views_per_hour,
        "latest_engagement_rate_percent": getattr(latest, "engagement_rate_percent", None),
        "latest_engagement_delta_rate_percent": getattr(latest, "engagement_delta_rate_percent", None),
        "latest_data_quality": getattr(latest, "data_quality", None),
        "latest_is_estimated": getattr(latest, "is_estimated", None),
        "counter_regression_detected": bool(
            any(getattr(row, "counter_regression_detected", False) for row in ordered)
        ),
    }
