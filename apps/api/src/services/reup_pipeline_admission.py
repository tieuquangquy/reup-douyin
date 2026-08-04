"""Work-in-progress control for the reup auto lane.

Per-job-type slots keep one machine alive, but they say nothing about *flow*. Starting auto
on fifty clips admits fifty clips: they all advance together, nothing finishes for hours,
and any incident costs the whole batch. Admitting a bounded number of clips at a time makes
finished videos arrive in a steady stream and keeps the blast radius small.

This module is pure policy — counting, ordering, deciding. Starting the work stays with the
orchestrator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable, Sequence

from src.enums import ReupQueueStatus
from src.services.reup_pipeline_meta import (
    PIPELINE_STEP_NEEDS_ATTENTION,
    PIPELINE_STEP_QUALITY_REVIEW,
    PIPELINE_STEP_TRANSLATION_REVIEW,
    PIPELINE_STEP_READY_FINAL,
    get_pipeline_step,
    is_auto_pipeline,
    meta_dict,
    set_pipeline_meta,
)

# Set on an item that the operator handed to the auto lane but that is waiting for a slot.
AWAITING_SLOT_KEY = "pipeline_awaiting_slot"

DEFAULT_MAX_ITEMS_IN_FLIGHT = 5

_TERMINAL_STEPS = frozenset(
    {
        PIPELINE_STEP_READY_FINAL,
        PIPELINE_STEP_NEEDS_ATTENTION,
        PIPELINE_STEP_QUALITY_REVIEW,
        PIPELINE_STEP_TRANSLATION_REVIEW,
    }
)

IN_FLIGHT_STATUSES: frozenset[ReupQueueStatus] = frozenset(
    {
        ReupQueueStatus.READY_FOR_PROCESSING,
        ReupQueueStatus.WAITING_FOR_MEDIA,
        ReupQueueStatus.WAITING_FOR_METADATA,
        ReupQueueStatus.PROCESSING,
    }
)


def max_items_in_flight(settings: object | None = None) -> int:
    if settings is None:
        from src.core.settings import get_settings

        settings = get_settings()
    try:
        return max(1, int(getattr(settings, "reup_max_items_in_flight", DEFAULT_MAX_ITEMS_IN_FLIGHT)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITEMS_IN_FLIGHT


def is_awaiting_slot(item: Any) -> bool:
    return bool(meta_dict(item).get(AWAITING_SLOT_KEY))


def is_in_flight(item: Any) -> bool:
    """Whether this item currently occupies one of the auto lane's slots."""
    if not is_auto_pipeline(item) or is_awaiting_slot(item):
        return False
    status = getattr(item, "status", None)
    if status not in IN_FLIGHT_STATUSES:
        return False
    return (get_pipeline_step(item) or "") not in _TERMINAL_STEPS


def count_in_flight(items: Iterable[Any]) -> int:
    return sum(1 for item in items if is_in_flight(item))


def _admission_sort_key(item: Any) -> tuple[int, datetime]:
    created = getattr(item, "created_at", None) or datetime.now(UTC)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (-int(getattr(item, "priority", 0) or 0), created)


def admission_plan(items: Sequence[Any], *, limit: int) -> list[Any]:
    """Parked items that may start now, most deserving first."""
    free = max(0, int(limit) - count_in_flight(items))
    if free <= 0:
        return []
    parked = [item for item in items if is_awaiting_slot(item)]
    parked.sort(key=_admission_sort_key)
    return parked[:free]


def park_for_slot(item: Any, *, mode: str) -> None:
    """Accept the operator's intent to automate without starting the work yet."""
    set_pipeline_meta(item, mode=mode, hold=False, extra={AWAITING_SLOT_KEY: True})


def clear_slot_wait(item: Any) -> None:
    meta = meta_dict(item)
    if AWAITING_SLOT_KEY in meta:
        meta.pop(AWAITING_SLOT_KEY, None)
        item.metadata_json = meta
