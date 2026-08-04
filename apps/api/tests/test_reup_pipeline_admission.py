"""Start-auto on 50 clips must not put 50 clips in flight.

Job-level slots keep the machine alive but do nothing about flow: fifty items admitted at
once all crawl forward together, so after hours you own fifty half-finished videos and zero
usable ones. Capping work in progress means clips finish in a steady stream, and a bad night
costs a handful of clips instead of the whole batch.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import ReupQueueStatus
from src.services.reup_pipeline_admission import (
    AWAITING_SLOT_KEY,
    admission_plan,
    count_in_flight,
    is_awaiting_slot,
    is_in_flight,
    max_items_in_flight,
)
from src.services.reup_pipeline_meta import (
    PIPELINE_MODE_AUTO_TO_RENDER,
    PIPELINE_STEP_NEEDS_ATTENTION,
    PIPELINE_STEP_READY_FINAL,
)

BASE = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)


def make_item(
    *,
    mode: str | None = PIPELINE_MODE_AUTO_TO_RENDER,
    step: str = "analyze_audio",
    status: ReupQueueStatus = ReupQueueStatus.PROCESSING,
    awaiting: bool = False,
    age_minutes: int = 0,
) -> SimpleNamespace:
    meta: dict[str, object] = {"pipeline_step": step}
    if mode is not None:
        meta["pipeline_mode"] = mode
    if awaiting:
        meta[AWAITING_SLOT_KEY] = True
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        metadata_json=meta,
        created_at=BASE + timedelta(minutes=age_minutes),
        priority=0,
    )


class InFlightTests(unittest.TestCase):
    def test_a_working_auto_item_is_in_flight(self) -> None:
        self.assertTrue(is_in_flight(make_item()))

    def test_a_parked_item_is_not_in_flight(self) -> None:
        item = make_item(awaiting=True, status=ReupQueueStatus.READY_FOR_PROCESSING)
        self.assertTrue(is_awaiting_slot(item))
        self.assertFalse(is_in_flight(item))

    def test_finished_and_stranded_items_release_their_slot(self) -> None:
        self.assertFalse(is_in_flight(make_item(step=PIPELINE_STEP_READY_FINAL)))
        self.assertFalse(
            is_in_flight(
                make_item(
                    step=PIPELINE_STEP_NEEDS_ATTENTION,
                    status=ReupQueueStatus.FAILED_NEEDS_ATTENTION,
                )
            )
        )

    def test_manual_items_do_not_consume_auto_slots(self) -> None:
        self.assertFalse(is_in_flight(make_item(mode=None)))

    def test_count_ignores_everything_but_live_auto_work(self) -> None:
        items = [
            make_item(),
            make_item(),
            make_item(awaiting=True),
            make_item(mode=None),
            make_item(step=PIPELINE_STEP_READY_FINAL),
        ]
        self.assertEqual(count_in_flight(items), 2)


class AdmissionPlanTests(unittest.TestCase):
    def test_nothing_is_admitted_while_the_floor_is_full(self) -> None:
        items = [make_item(), make_item(), make_item(awaiting=True)]
        self.assertEqual(admission_plan(items, limit=2), [])

    def test_only_the_free_slots_are_filled(self) -> None:
        parked = [make_item(awaiting=True, age_minutes=n) for n in range(5)]
        admitted = admission_plan([make_item(), *parked], limit=3)

        self.assertEqual(len(admitted), 2)

    def test_oldest_parked_item_goes_first(self) -> None:
        late = make_item(awaiting=True, age_minutes=30)
        early = make_item(awaiting=True, age_minutes=1)

        admitted = admission_plan([late, early], limit=1)

        self.assertEqual([item.id for item in admitted], [early.id])

    def test_priority_beats_age(self) -> None:
        early = make_item(awaiting=True, age_minutes=1)
        urgent = make_item(awaiting=True, age_minutes=30)
        urgent.priority = 10

        admitted = admission_plan([early, urgent], limit=1)

        self.assertEqual([item.id for item in admitted], [urgent.id])

    def test_empty_queue_admits_nothing(self) -> None:
        self.assertEqual(admission_plan([], limit=5), [])


class LimitTests(unittest.TestCase):
    def test_limit_comes_from_settings(self) -> None:
        self.assertEqual(max_items_in_flight(SimpleNamespace(reup_max_items_in_flight=6)), 6)

    def test_limit_has_a_floor_of_one(self) -> None:
        self.assertEqual(max_items_in_flight(SimpleNamespace(reup_max_items_in_flight=0)), 1)

    def test_garbage_falls_back_to_the_default(self) -> None:
        self.assertGreaterEqual(max_items_in_flight(SimpleNamespace(reup_max_items_in_flight="lots")), 1)


class OrchestratorAdmitTests(unittest.TestCase):
    def _orchestrator(self, items: list[SimpleNamespace]):
        from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

        db = MagicMock()
        db.scalars.return_value.all.return_value = items
        return ReupPipelineOrchestrator(db)

    def test_freed_slot_starts_the_next_parked_clip(self) -> None:
        parked = make_item(awaiting=True, status=ReupQueueStatus.READY_FOR_PROCESSING)
        orchestrator = self._orchestrator([make_item(step=PIPELINE_STEP_READY_FINAL), parked])

        with (
            patch("src.core.settings.get_settings", return_value=SimpleNamespace(reup_max_items_in_flight=2)),
            patch.object(orchestrator, "_ensure_download", return_value=True) as ensure,
        ):
            admitted = orchestrator.admit_waiting_items(workspace_id=uuid4())

        self.assertEqual(admitted, 1)
        ensure.assert_called_once_with(parked)
        self.assertFalse(is_awaiting_slot(parked), "An admitted item must stop looking parked")

    def test_full_floor_leaves_parked_clips_alone(self) -> None:
        parked = make_item(awaiting=True, status=ReupQueueStatus.READY_FOR_PROCESSING)
        orchestrator = self._orchestrator([make_item(), make_item(), parked])

        with (
            patch("src.core.settings.get_settings", return_value=SimpleNamespace(reup_max_items_in_flight=2)),
            patch.object(orchestrator, "_ensure_download") as ensure,
        ):
            admitted = orchestrator.admit_waiting_items(workspace_id=uuid4())

        self.assertEqual(admitted, 0)
        ensure.assert_not_called()
        self.assertTrue(is_awaiting_slot(parked))

    def test_a_failed_admission_does_not_block_the_rest(self) -> None:
        broken = make_item(awaiting=True, age_minutes=1)
        healthy = make_item(awaiting=True, age_minutes=2)
        orchestrator = self._orchestrator([broken, healthy])

        def ensure(item: SimpleNamespace) -> bool:
            if item.id == broken.id:
                raise RuntimeError("douyin refused")
            return True

        with (
            patch("src.core.settings.get_settings", return_value=SimpleNamespace(reup_max_items_in_flight=5)),
            patch.object(orchestrator, "_ensure_download", side_effect=ensure),
        ):
            admitted = orchestrator.admit_waiting_items(workspace_id=uuid4())

        self.assertEqual(admitted, 1)
        self.assertFalse(is_awaiting_slot(healthy))


if __name__ == "__main__":
    unittest.main()
