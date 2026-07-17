from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Iterable


def resolve_time_window(window: str, start: datetime | None = None, end: datetime | None = None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if window == "today":
        today_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        return today_start, now
    if window == "last_30_days":
        return now - timedelta(days=30), now
    if window == "custom" and start and end:
        return start, end
    return now - timedelta(days=7), now


def percent(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100, 2)


def count_by_day(items: Iterable[datetime | None]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        if item is not None:
            counts[item.date().isoformat()] += 1
    return dict(sorted(counts.items()))


def day_key(value: datetime | date | None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()
