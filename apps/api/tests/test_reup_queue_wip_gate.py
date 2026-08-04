"""Start auto on a full lane queues the clip instead of piling on.

The operator can select fifty clips and press Start auto; the promise is that all fifty get
done, not that all fifty start now. Parked clips must carry their chosen mode and start on
their own when a slot frees up.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobType, ReupQueueAction, ReupQueueStatus
from src.services.reup_pipeline_admission import is_awaiting_slot, is_in_flight
from src.services.reup_pipeline_meta import (
    PIPELINE_MODE_AUTO_TO_RENDER,
    PIPELINE_STEP_DOWNLOAD,
    get_pipeline_mode,
    get_pipeline_step,
)
from src.services.reup_queue_service import ReupQueueService

WORKSPACE = uuid4()


def make_item(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "workspace_id": WORKSPACE,
        "status": ReupQueueStatus.READY_FOR_PROCESSING,
        "media_prep_status": None,
        "metadata_json": {},
        "created_at": datetime(2026, 7, 26, tzinfo=UTC),
        "priority": 0,
        "job_id": None,
        "started_at": None,
        "held_at": None,
        "blocked_at": None,
        "blocked_reason": None,
        "failed_at": None,
        "last_error_code": None,
        "last_error_message": None,
        "last_action_note": None,
        "source_video_id": uuid4(),
        "video_candidate_id": uuid4(),
        "last_action": None,
        "last_action_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def in_flight_item() -> SimpleNamespace:
    return make_item(
        status=ReupQueueStatus.PROCESSING,
        metadata_json={"pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER, "pipeline_step": "ocr"},
    )


class StartAutoGateTests(unittest.TestCase):
    def _apply(self, item: SimpleNamespace, others: list[SimpleNamespace], *, limit: int):
        db = MagicMock()
        db.get.return_value = item
        db.scalars.return_value.all.return_value = [item, *others]
        service = ReupQueueService(db)

        with (
            patch("src.core.settings.get_settings", return_value=SimpleNamespace(reup_max_items_in_flight=limit)),
            patch.object(service, "get_item", return_value=item),
            patch.object(service, "_ensure_download_job_id", return_value=uuid4()) as ensure,
        ):
            service.apply_action(
                item.id,
                action=ReupQueueAction.START_AUTO_PIPELINE,
                pipeline_mode=PIPELINE_MODE_AUTO_TO_RENDER,
            )
        return ensure

    def test_free_lane_starts_the_download_immediately(self) -> None:
        item = make_item()

        ensure = self._apply(item, [], limit=2)

        ensure.assert_called_once()
        self.assertFalse(is_awaiting_slot(item))
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_MEDIA)
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_DOWNLOAD)

    def test_full_lane_parks_the_clip_without_touching_douyin(self) -> None:
        item = make_item()

        ensure = self._apply(item, [in_flight_item(), in_flight_item()], limit=2)

        ensure.assert_not_called()
        self.assertTrue(is_awaiting_slot(item), "The clip must be queued, not started")
        self.assertEqual(get_pipeline_mode(item), PIPELINE_MODE_AUTO_TO_RENDER, "Its chosen mode must survive")
        self.assertFalse(is_in_flight(item), "A parked clip must not hold a slot")
        self.assertIsNotNone(item.last_action_note)
        self.assertIn("slot", str(item.last_action_note).lower())

    def test_parked_clip_stays_actionable(self) -> None:
        item = make_item()

        self._apply(item, [in_flight_item(), in_flight_item()], limit=2)

        self.assertEqual(item.status, ReupQueueStatus.READY_FOR_PROCESSING)


class TerminalJobAdmitsTests(unittest.TestCase):
    def test_finishing_a_job_pulls_the_next_clip_in(self) -> None:
        from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

        item = in_flight_item()
        db = MagicMock()
        orchestrator = ReupPipelineOrchestrator(db)
        job = SimpleNamespace(
            id=uuid4(),
            status=JobStatus.COMPLETED,
            job_type=JobType.RENDER_FINAL,
            workspace_id=WORKSPACE,
            error_code=None,
            error_message=None,
        )

        with (
            patch.object(orchestrator, "_find_items_for_job", return_value=[item]),
            patch.object(orchestrator, "_advance_after_success", return_value=True),
            patch.object(orchestrator, "admit_waiting_items", return_value=1) as admit,
        ):
            orchestrator.on_job_terminal(job)

        admit.assert_called_once_with(workspace_id=WORKSPACE)

    def test_admission_crash_does_not_break_job_completion(self) -> None:
        from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

        item = in_flight_item()
        orchestrator = ReupPipelineOrchestrator(MagicMock())
        job = SimpleNamespace(
            id=uuid4(),
            status=JobStatus.COMPLETED,
            job_type=JobType.RENDER_FINAL,
            workspace_id=WORKSPACE,
            error_code=None,
            error_message=None,
        )

        with (
            patch.object(orchestrator, "_find_items_for_job", return_value=[item]),
            patch.object(orchestrator, "_advance_after_success", return_value=True),
            patch.object(orchestrator, "admit_waiting_items", side_effect=RuntimeError("db hiccup")),
        ):
            self.assertEqual(orchestrator.on_job_terminal(job), 1)


if __name__ == "__main__":
    unittest.main()
