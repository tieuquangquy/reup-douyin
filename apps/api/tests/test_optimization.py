from __future__ import annotations

import unittest

from src.optimization.services.outcome_score_helpers import clamp_score, outcome_label, weighted_component
from src.optimization.services.automation_policy_service import AutomationPolicyService


class OptimizationHelperTests(unittest.TestCase):
    def test_weighted_component_is_clamped_and_weighted(self) -> None:
        component = weighted_component("test", "Test", {"raw": 1}, 120, 25)
        self.assertEqual(component.subscore, 100)
        self.assertEqual(component.weighted_contribution, 25)
        self.assertEqual(clamp_score(-10), 0)

    def test_outcome_label_thresholds(self) -> None:
        self.assertEqual(outcome_label(85), "strong")
        self.assertEqual(outcome_label(70), "usable")
        self.assertEqual(outcome_label(50), "needs_work")
        self.assertEqual(outcome_label(30), "weak")

    def test_schedule_policy_blocks_low_confidence(self) -> None:
        class Draft:
            status = "READY"
            assigned_platform_account_id = "account-1"

        result = AutomationPolicyService().evaluate_auto_schedule(draft=Draft(), confidence_label="medium", warnings=[])
        self.assertFalse(result["can_auto_fill_schedule"])
        self.assertIn("Schedule confidence is not high enough for auto-fill.", result["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
