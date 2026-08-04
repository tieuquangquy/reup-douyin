from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import ReupQueueBatchAction, ReupQueueStatus
from src.services.export_handoff_service import ExportHandoffService
from src.services.reup_queue_batch_limits import apply_start_processing_batch_cap


class StartProcessingBatchLimitTests(unittest.TestCase):
    def test_apply_start_processing_batch_cap_keeps_first_n_preserves_order(self) -> None:
        ids = [uuid4() for _ in range(5)]
        accepted, overflow = apply_start_processing_batch_cap(ids, limit=3)

        self.assertEqual(accepted, ids[:3])
        self.assertEqual(overflow, ids[3:])

    def test_apply_start_processing_batch_cap_no_overflow_when_at_or_under_limit(self) -> None:
        ids = [uuid4() for _ in range(3)]
        accepted, overflow = apply_start_processing_batch_cap(ids, limit=3)

        self.assertEqual(accepted, ids)
        self.assertEqual(overflow, [])

    def test_batch_start_processing_skips_overflow_beyond_configured_limit(self) -> None:
        item_ids = [uuid4() for _ in range(4)]
        fake_db = MagicMock()
        updated = MagicMock()
        updated.status = ReupQueueStatus.WAITING_FOR_MEDIA

        with (
            patch("src.services.export_handoff_service.get_settings") as mock_settings,
            patch("src.services.export_handoff_service.ReupQueueService") as mock_queue_cls,
        ):
            mock_settings.return_value.reup_queue_start_processing_batch_limit = 2
            mock_queue_cls.return_value.apply_action.return_value = updated

            result = ExportHandoffService(fake_db).run_batch_action(
                action=ReupQueueBatchAction.START_PROCESSING,
                item_ids=item_ids,
                note="Start capped batch",
            )

        self.assertEqual(result.requested_count, 4)
        self.assertEqual(result.succeeded_count, 2)
        self.assertEqual(result.skipped_count, 2)
        self.assertEqual(mock_queue_cls.return_value.apply_action.call_count, 2)
        self.assertEqual(result.results[2].reason_code, "START_PROCESSING_BATCH_LIMIT")
        self.assertEqual(result.results[3].reason_code, "START_PROCESSING_BATCH_LIMIT")
        self.assertEqual(result.results[2].item_id, item_ids[2])
        self.assertEqual(result.results[3].item_id, item_ids[3])

    def test_batch_start_auto_accepts_everything_because_the_lane_parks_overflow(self) -> None:
        """The manual cap protected the download session before parking existed.

        Auto now has its own admission control (`REUP_MAX_ITEMS_IN_FLIGHT`): extra clips are
        queued and start themselves. Rejecting them here would ask the operator to babysit a
        second batch for no reason.
        """
        item_ids = [uuid4() for _ in range(4)]
        updated = MagicMock()
        updated.status = ReupQueueStatus.READY_FOR_PROCESSING

        with (
            patch("src.services.export_handoff_service.get_settings") as mock_settings,
            patch("src.services.export_handoff_service.ReupQueueService") as mock_queue_cls,
        ):
            mock_settings.return_value.reup_queue_start_processing_batch_limit = 2
            mock_queue_cls.return_value.apply_action.return_value = updated

            result = ExportHandoffService(MagicMock()).run_batch_action(
                action=ReupQueueBatchAction.START_AUTO_PIPELINE,
                item_ids=item_ids,
                note="Start auto on everything",
            )

        self.assertEqual(result.succeeded_count, 4)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(mock_queue_cls.return_value.apply_action.call_count, 4)
        self.assertFalse(
            any(entry.reason_code == "START_PROCESSING_BATCH_LIMIT" for entry in result.results),
            "Auto clips must queue, not be rejected",
        )


if __name__ == "__main__":
    unittest.main()
