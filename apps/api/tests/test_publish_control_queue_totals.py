from types import SimpleNamespace
import unittest
from uuid import uuid4

from src.enums import PublishTargetPlatform
from src.publish_routing.services.control_queue_service import ControlQueueService


class _FakeDb:
    def __init__(self) -> None:
        self.counts = iter([240, 13, 7, 17])

    def scalars(self, _statement):
        return []

    def scalar(self, _statement):
        return next(self.counts)


class PublishControlQueueTotalsTests(unittest.TestCase):
    def test_totals_are_independent_from_bounded_detail_rows(self) -> None:
        service = object.__new__(ControlQueueService)
        service.db = _FakeDb()
        service.workspace_id = uuid4()
        service.health_service = SimpleNamespace(list_account_health=lambda **_kwargs: [])
        service.recommendation_service = SimpleNamespace()

        queue = service.queue(platform=PublishTargetPlatform.FACEBOOK_REELS, limit=1)

        self.assertEqual(queue.unassigned_drafts, [])
        self.assertEqual(queue.unassigned_total, 240)
        self.assertEqual(queue.assigned_total, 13)
        self.assertEqual(queue.scheduled_total, 7)
        self.assertEqual(queue.needs_attention_total, 17)


if __name__ == "__main__":
    unittest.main()
