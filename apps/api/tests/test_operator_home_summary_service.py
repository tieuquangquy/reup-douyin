from __future__ import annotations

import unittest
from datetime import UTC, datetime

from src.services.operator_home_summary_service import (
    OperatorHomeAggregate,
    OutputQaCounts,
    build_attention_breakdown,
    build_decision_metrics,
    build_output_qa_summary,
    oldest_known_at,
    operator_home_status,
)
from src.schemas.operator_home import OperatorHomePriorityItem
from src.schemas.pipeline_dashboard import PipelineDashboardMetric, PipelineDashboardStage
from src.services.operator_home_summary_service import OperatorHomeSummaryService


class OperatorHomeSummaryServiceTests(unittest.TestCase):
    def test_decision_metrics_share_one_aggregate_authority(self) -> None:
        aggregate = OperatorHomeAggregate(
            needs_attention=7,
            in_progress=3,
            awaiting_review=5,
            ready_downstream=2,
            critical_count=1,
        )

        metrics = build_decision_metrics(aggregate)

        self.assertEqual(
            {metric.key: metric.value for metric in metrics},
            {
                "needs_attention": 7,
                "in_progress": 3,
                "awaiting_review": 5,
                "ready_downstream": 2,
            },
        )
        self.assertEqual(operator_home_status(aggregate), "blocked")

    def test_status_distinguishes_attention_progress_and_quiet(self) -> None:
        self.assertEqual(operator_home_status(OperatorHomeAggregate(needs_attention=2)), "needs_attention")
        self.assertEqual(operator_home_status(OperatorHomeAggregate(in_progress=1)), "in_progress")
        self.assertEqual(operator_home_status(OperatorHomeAggregate(ready_downstream=1)), "healthy")
        self.assertEqual(operator_home_status(OperatorHomeAggregate()), "quiet")

    def test_output_qa_summary_keeps_all_canonical_buckets(self) -> None:
        summary = build_output_qa_summary(OutputQaCounts(passed=8, warned=3, failed=2, ungraded=1))

        self.assertEqual(summary.passed, 8)
        self.assertEqual(summary.warned, 3)
        self.assertEqual(summary.failed, 2)
        self.assertEqual(summary.ungraded, 1)
        self.assertEqual(summary.total, 14)

    def test_attention_breakdown_excludes_manual_review_warning_overlap(self) -> None:
        priorities = [
            OperatorHomePriorityItem(
                id="render-failed",
                severity="critical",
                stage_key="render",
                title="Render failures",
                detail="Two renders failed.",
                count=2,
                href="/production/output-review",
                recommended_action="Inspect failed renders.",
            ),
            OperatorHomePriorityItem(
                id="capture-warning",
                severity="warning",
                stage_key="capture",
                title="Capture warning",
                detail="Three captures need attention.",
                count=3,
                href="/selection/capture-inbox",
                recommended_action="Inspect capture inbox.",
            ),
            OperatorHomePriorityItem(
                id="output-review-warning",
                severity="warning",
                stage_key="output_review",
                title="Output review",
                detail="Four outputs need manual review.",
                count=4,
                href="/production/output-review",
                recommended_action="Review outputs.",
            ),
        ]

        breakdown = build_attention_breakdown(priorities, manual_review_count=7)

        self.assertEqual(breakdown.critical, 2)
        self.assertEqual(breakdown.warning, 3)
        self.assertEqual(breakdown.manual_review, 7)
        self.assertEqual(breakdown.total, 12)

    def test_pipeline_stage_chart_buckets_are_exclusive(self) -> None:
        service = OperatorHomeSummaryService.__new__(OperatorHomeSummaryService)
        review = PipelineDashboardStage(
            key="review",
            label="Review",
            description="",
            status="needs_attention",
            primary_count=5,
            primary_label="Review backlog",
            secondary_count=2,
            secondary_label="Approved not queued",
            attention_count=7,
            review_count=5,
            ready_count=2,
            total_count=7,
            href="/selection/review-board",
            next_action="Review candidates.",
        )
        queue = PipelineDashboardStage(
            key="reup_queue",
            label="Reup Queue",
            description="",
            status="blocked",
            primary_count=10,
            primary_label="Active",
            secondary_count=2,
            secondary_label="Ready",
            metrics=[PipelineDashboardMetric(key="failed", label="Failed", value=1)],
            attention_count=5,
            waiting_count=4,
            running_count=3,
            failed_count=1,
            ready_count=2,
            total_count=10,
            href="/selection/reup-queue",
            next_action="Inspect queue.",
        )

        review_home, queue_home = service._home_stages([review, queue])

        self.assertEqual(
            (review_home.waiting_count, review_home.review_count),
            (0, 5),
        )
        self.assertEqual(
            (
                queue_home.waiting_count,
                queue_home.running_count,
                queue_home.failed_count,
                queue_home.ready_count,
            ),
            (4, 3, 1, 2),
        )

    def test_oldest_known_at_ignores_missing_authorities(self) -> None:
        older = datetime(2026, 7, 25, 8, 0, tzinfo=UTC)
        newer = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)

        self.assertEqual(oldest_known_at(None, newer, older), older)
        self.assertIsNone(oldest_known_at(None, None))


if __name__ == "__main__":
    unittest.main()
