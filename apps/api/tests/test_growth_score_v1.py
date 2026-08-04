from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from uuid import uuid4

from src.analytics.services.publication_metrics_helpers import recompute_snapshot_series
from src.enums import JobType
from src.growth_intelligence.services.growth_score_service import GrowthScoreService
from src.services.job_templates import get_step_templates


def _snapshot(observed_at: datetime, *, views: int, likes: int):
    return SimpleNamespace(
        id=uuid4(),
        observed_at=observed_at,
        view_count=views,
        like_count=likes,
        comment_count=0,
        share_count=0,
        save_count=0,
        data_quality="COMPLETE",
        is_estimated=False,
        counter_regression_detected=False,
        views_per_hour=None,
        engagement_rate_percent=None,
        engagement_delta_rate_percent=None,
    )


class GrowthScoreV1Tests(unittest.TestCase):
    def test_score_keeps_growth_components_separate_from_affiliate_fit(self) -> None:
        now = datetime.now(UTC)
        snapshots = [
            _snapshot(now - timedelta(hours=2), views=100, likes=10),
            _snapshot(now - timedelta(hours=1), views=200, likes=20),
            _snapshot(now, views=500, likes=50),
        ]
        recompute_snapshot_series(snapshots)
        publication = SimpleNamespace(id=uuid4(), published_at=now - timedelta(hours=12))

        result = GrowthScoreService.calculate(publication, snapshots)

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["confidence"], "HIGH")
        self.assertEqual(result["growth_score"], 93.0)
        self.assertEqual(
            result["score_breakdown"],
            {
                "view_velocity": 28.0,
                "view_acceleration": 25.0,
                "engagement_quality": 20.0,
                "publication_freshness": 10.0,
                "data_quality": 10.0,
            },
        )
        self.assertNotIn("affiliate", result["score_breakdown"])

    def test_baseline_only_is_not_given_a_growth_score(self) -> None:
        now = datetime.now(UTC)
        snapshot = _snapshot(now, views=100, likes=10)
        recompute_snapshot_series([snapshot])

        result = GrowthScoreService.calculate(
            SimpleNamespace(id=uuid4(), published_at=now),
            [snapshot],
        )

        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["growth_score"])
        self.assertEqual(result["confidence"], "LOW")

    def test_opportunity_recommendation_uses_two_dimensional_gate(self) -> None:
        common = {
            "growth_status": "READY",
            "confidence": "HIGH",
            "growth_is_stale": False,
            "product_active": True,
            "product_availability": "IN_STOCK",
        }
        self.assertEqual(
            GrowthScoreService.recommendation(growth_score=82, affiliate_fit_score=79, **common)[0],
            "PRIORITY",
        )
        self.assertEqual(
            GrowthScoreService.recommendation(growth_score=82, affiliate_fit_score=45, **common)[0],
            "DO_NOT_PLACE",
        )
        self.assertEqual(
            GrowthScoreService.recommendation(growth_score=35, affiliate_fit_score=80, **common)[0],
            "MONITOR",
        )

    def test_stale_or_missing_signal_never_becomes_priority(self) -> None:
        recommendation, _ = GrowthScoreService.recommendation(
            growth_score=90,
            growth_status="READY",
            confidence="HIGH",
            affiliate_fit_score=90,
            growth_is_stale=True,
            product_active=True,
            product_availability="IN_STOCK",
        )
        self.assertEqual(recommendation, "INSUFFICIENT_DATA")

    def test_growth_score_job_has_one_persist_boundary(self) -> None:
        self.assertEqual(
            [step.key for step in get_step_templates(JobType.CALCULATE_GROWTH_SCORE)],
            ["validate_publication", "load_metric_evidence", "calculate_and_persist", "finalize"],
        )

    def test_growth_routes_are_registered(self) -> None:
        from src.main import app

        paths = app.openapi()["paths"]
        self.assertIn("/platform-publications/{publication_id}/growth-score-jobs", paths)
        self.assertIn("/affiliate-opportunities/review-queue", paths)


if __name__ == "__main__":
    unittest.main()
