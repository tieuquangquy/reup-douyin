from __future__ import annotations

import unittest
from unittest.mock import Mock
from uuid import uuid4

from src.services.pipeline_dashboard_service import PipelineCounts, PipelineDashboardService


class PipelineDashboardServiceTests(unittest.TestCase):
    def test_stage_status_and_attention_items_surface_operator_blockers(self) -> None:
        service = PipelineDashboardService(Mock(), workspace_id=uuid4())
        counts = PipelineCounts(
            captures_last_24h=2,
            capture_ready_items=3,
            capture_failed_items=1,
            review_backlog=4,
            approved_candidates=5,
            approved_not_queued=2,
            queue_active=6,
            queue_waiting_media=1,
            queue_waiting_metadata=1,
            queue_failed=2,
            queue_ready_to_export=3,
            export_ready=2,
            export_failed=0,
            handoff_ready=1,
            handoff_failed=0,
            publish_ready=1,
            publish_scheduled=1,
            publish_active_drafts=2,
            publish_published=8,
            publish_failed_drafts=1,
            publish_active_attempts=1,
            publish_failed_attempts=1,
            publish_needs_reconciliation=1,
        )

        stages = service._stages(counts)
        attention = service._attention_items(counts)
        overall = service._overall_status(stages, attention)
        summary = service._summary_metrics(counts, attention)

        self.assertEqual([stage.key for stage in stages], ["capture", "review", "reup_queue", "export_package", "publish_handoff", "publish_progress"])
        self.assertEqual(stages[0].status, "blocked")
        self.assertEqual(stages[2].status, "blocked")
        self.assertEqual(stages[5].status, "blocked")
        self.assertEqual(overall, "blocked")
        self.assertTrue(any(item.severity == "critical" and item.stage_key == "capture" for item in attention))
        self.assertTrue(any(item.title == "Publish issues" and item.count == 3 for item in attention))
        self.assertEqual(next(metric.value for metric in summary if metric.key == "active_backlog"), 12)
        self.assertEqual(next(metric.value for metric in summary if metric.key == "export_ready"), 5)

    def test_quiet_counts_create_empty_command_view_without_blockers(self) -> None:
        service = PipelineDashboardService(Mock(), workspace_id=uuid4())
        counts = PipelineCounts(
            captures_last_24h=0,
            capture_ready_items=0,
            capture_failed_items=0,
            review_backlog=0,
            approved_candidates=0,
            approved_not_queued=0,
            queue_active=0,
            queue_waiting_media=0,
            queue_waiting_metadata=0,
            queue_failed=0,
            queue_ready_to_export=0,
            export_ready=0,
            export_failed=0,
            handoff_ready=0,
            handoff_failed=0,
            publish_ready=0,
            publish_scheduled=0,
            publish_active_drafts=0,
            publish_published=0,
            publish_failed_drafts=0,
            publish_active_attempts=0,
            publish_failed_attempts=0,
            publish_needs_reconciliation=0,
        )

        stages = service._stages(counts)
        attention = service._attention_items(counts)

        self.assertEqual(service._overall_status(stages, attention), "quiet")
        self.assertEqual(attention, [])
        self.assertTrue(all(stage.status == "quiet" for stage in stages))
        self.assertEqual(service._headline("quiet", counts, attention), "Pipeline is quiet; start with Capture Inbox when new source content is ready.")


if __name__ == "__main__":
    unittest.main()
