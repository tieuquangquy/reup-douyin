"""Safe batch limits for Reup Queue operator actions."""

from __future__ import annotations

from uuid import UUID

DEFAULT_START_PROCESSING_BATCH_LIMIT = 30


def apply_start_processing_batch_cap(
    item_ids: list[UUID],
    *,
    limit: int = DEFAULT_START_PROCESSING_BATCH_LIMIT,
) -> tuple[list[UUID], list[UUID]]:
    """Split ids into (accepted, overflow) preserving order.

    Downloads share one Playwright browser session; oversized START_PROCESSING
    batches risk lock contention, orphan Chromium, and operator stalls.
    """
    if limit < 1:
        raise ValueError("start processing batch limit must be >= 1")
    if len(item_ids) <= limit:
        return list(item_ids), []
    return list(item_ids[:limit]), list(item_ids[limit:])
