from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import unittest

from src.enums import PlatformAccountHealthStatus, PlatformAccountStatus
from src.publish_routing.services.routing_helpers import classify_account_health, health_score_boost, percent


class PublishRoutingHelperTests(unittest.TestCase):
    def test_account_health_classification_healthy(self) -> None:
        health, reasons = classify_account_health(
            account_status=PlatformAccountStatus.ACTIVE,
            is_on_hold=False,
            cooldown_until=None,
            attempts_7d=5,
            success_rate_percent=100,
            failed_7d=0,
            needs_reconciliation_count=0,
        )

        self.assertEqual(health, PlatformAccountHealthStatus.HEALTHY)
        self.assertIn("No recent account health blockers", reasons)

    def test_account_health_classification_held(self) -> None:
        health, reasons = classify_account_health(
            account_status=PlatformAccountStatus.ACTIVE,
            is_on_hold=True,
            cooldown_until=datetime.now(UTC) + timedelta(hours=1),
            attempts_7d=0,
            success_rate_percent=0,
            failed_7d=0,
            needs_reconciliation_count=0,
        )

        self.assertEqual(health, PlatformAccountHealthStatus.HELD)
        self.assertIn("Account is on manual hold", reasons)
        self.assertIn("Account is in cooldown window", reasons)

    def test_account_health_classification_unhealthy(self) -> None:
        health, reasons = classify_account_health(
            account_status=PlatformAccountStatus.ACTIVE,
            is_on_hold=False,
            cooldown_until=None,
            attempts_7d=4,
            success_rate_percent=25,
            failed_7d=3,
            needs_reconciliation_count=0,
        )

        self.assertEqual(health, PlatformAccountHealthStatus.UNHEALTHY)
        self.assertTrue(reasons)

    def test_score_boosts_make_unhealthy_non_recommended(self) -> None:
        self.assertGreater(health_score_boost(PlatformAccountHealthStatus.HEALTHY), health_score_boost(PlatformAccountHealthStatus.DEGRADED))
        self.assertLess(health_score_boost(PlatformAccountHealthStatus.UNHEALTHY), -100)
        self.assertEqual(percent(2, 4), 50)
        self.assertEqual(percent(1, 0), 0)


if __name__ == "__main__":
    unittest.main()
