from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.api.routes.reup_queue import list_reup_queue_items
from src.enums import ReupQueueStatus
from src.schemas.reup_queue import ReupQueueListResponse
from src.services.reup_queue_service import ReupQueueService


class ReupQueueListFilterPaginationTests(unittest.TestCase):
    def test_list_response_includes_status_counts(self) -> None:
        payload = ReupQueueListResponse(
            items=[],
            total_count=2,
            limit=25,
            offset=0,
            status_counts={"READY_FOR_PROCESSING": 2, "WAITING_FOR_MEDIA": 5},
        )
        self.assertEqual(payload.total_count, 2)
        self.assertEqual(payload.status_counts["READY_FOR_PROCESSING"], 2)
        self.assertEqual(payload.status_counts["WAITING_FOR_MEDIA"], 5)

    def test_list_items_filters_by_statuses_and_returns_global_counts(self) -> None:
        ready = SimpleNamespace(id=uuid4(), status=ReupQueueStatus.READY_FOR_PROCESSING)
        db = MagicMock()
        # scalars().unique() → page items
        db.scalars.return_value.unique.return_value = [ready]
        # first scalar = filtered total, second = status_counts rows via execute
        db.scalar.return_value = 1
        db.execute.return_value.all.return_value = [
            (ReupQueueStatus.READY_FOR_PROCESSING, 1),
            (ReupQueueStatus.WAITING_FOR_MEDIA, 4),
        ]

        service = ReupQueueService(db)
        items, total, status_counts = service.list_items(
            statuses=[ReupQueueStatus.READY_FOR_PROCESSING],
            limit=25,
            offset=0,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(total, 1)
        self.assertEqual(status_counts.get("READY_FOR_PROCESSING"), 1)
        self.assertEqual(status_counts.get("WAITING_FOR_MEDIA"), 4)

    def test_list_route_passes_statuses_and_status_counts(self) -> None:
        service = MagicMock()
        service.list_items.return_value = ([], 0, {"READY_FOR_PROCESSING": 3})
        response = list_reup_queue_items(
            status_filter=None,
            statuses=[ReupQueueStatus.READY_FOR_PROCESSING],
            include_dismissed=False,
            sort="active_first",
            limit=25,
            offset=0,
            service=service,
        )
        self.assertEqual(response.status_counts["READY_FOR_PROCESSING"], 3)
        service.list_items.assert_called_once()
        kwargs = service.list_items.call_args.kwargs
        self.assertEqual(kwargs["statuses"], [ReupQueueStatus.READY_FOR_PROCESSING])
        self.assertEqual(kwargs["sort"], "active_first")


if __name__ == "__main__":
    unittest.main()
