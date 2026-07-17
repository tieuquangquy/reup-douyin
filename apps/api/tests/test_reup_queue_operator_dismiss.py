from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from src.enums import ReupQueueAction, ReupQueueStatus
from src.services.reup_queue_service import (
    OPERATOR_CLEARABLE_STATUSES,
    available_action_values,
    available_actions_for_item,
)


class ReupQueueOperatorDismissTests(unittest.TestCase):
    def test_terminal_statuses_expose_dismiss_action(self) -> None:
        for status in (ReupQueueStatus.COMPLETED, ReupQueueStatus.CANCELLED):
            actions = available_action_values(self._item(status=status))
            self.assertEqual(actions, {ReupQueueAction.DISMISS})

    def test_failed_needs_attention_exposes_dismiss_action(self) -> None:
        actions = available_action_values(self._item(status=ReupQueueStatus.FAILED_NEEDS_ATTENTION))
        self.assertIn(ReupQueueAction.DISMISS, actions)

    def test_dismiss_action_has_operator_copy(self) -> None:
        actions = available_actions_for_item(self._item(status=ReupQueueStatus.CANCELLED))
        dismiss = next(action for action in actions if action.action == ReupQueueAction.DISMISS)
        self.assertEqual(dismiss.label, "Dismiss")

    def test_clearable_statuses_match_operator_cleanup_contract(self) -> None:
        self.assertEqual(
            OPERATOR_CLEARABLE_STATUSES,
            {
                ReupQueueStatus.COMPLETED,
                ReupQueueStatus.CANCELLED,
                ReupQueueStatus.FAILED_NEEDS_ATTENTION,
            },
        )

    def _item(self, *, status: ReupQueueStatus):
        return type(
            "QueueItem",
            (),
            {
                "status": status,
                "media_prep_status": None,
            },
        )()


if __name__ == "__main__":
    unittest.main()
