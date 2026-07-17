from datetime import UTC, datetime
from types import SimpleNamespace
import unittest

from src.analytics.services.publish_health_helpers import percent, resolve_time_window
from src.analytics.services.publish_health_service import PublishHealthService
from src.enums import ExternalPublicationStatus, OperatorFeedbackQualityLabel, PublishAttemptStatus, PublishDraftStatus
from src.schemas.analytics import PublicationOutcomeItem


class PublishHealthAnalyticsTests(unittest.TestCase):
    def test_percent_handles_empty_total(self) -> None:
        self.assertEqual(percent(1, 0), 0.0)
        self.assertEqual(percent(1, 4), 25.0)

    def test_time_window_defaults_to_last_7_days(self) -> None:
        start, end = resolve_time_window("last_7_days")
        self.assertGreater((end - start).days, 6)

    def test_failure_group_maps_operator_friendly_categories(self) -> None:
        service = object.__new__(PublishHealthService)
        self.assertEqual(PublishHealthService._failure_group(service, "auth_token_invalid"), "auth_or_account_config")
        self.assertEqual(PublishHealthService._failure_group(service, "upload_failed"), "upload_or_transport_failure")
        self.assertEqual(PublishHealthService._failure_group(service, "gate_blocked"), "gate_or_policy_blocked")

    def test_pipeline_grouping_counts_feedback_and_reconciliation(self) -> None:
        service = object.__new__(PublishHealthService)
        outcomes = [
            PublicationOutcomeItem(
                publish_draft_id="00000000-0000-0000-0000-000000000001",
                source_video_id="00000000-0000-0000-0000-000000000011",
                platform="FACEBOOK_REELS",
                status=PublishDraftStatus.PUBLISHED,
                external_status=ExternalPublicationStatus.PUBLISHED,
                source_profile_name="Food Page",
                preset_name="safe_reup",
                niche_label="food",
                score=90,
                feedback_quality_label=OperatorFeedbackQualityLabel.GOOD,
            ),
            PublicationOutcomeItem(
                publish_draft_id="00000000-0000-0000-0000-000000000002",
                source_video_id="00000000-0000-0000-0000-000000000012",
                platform="FACEBOOK_REELS",
                status=PublishDraftStatus.NEEDS_ATTENTION,
                external_status=ExternalPublicationStatus.PARTIALLY_CONFIRMED,
                source_profile_name="Food Page",
                preset_name="safe_reup",
                niche_label="food",
                score=70,
                feedback_quality_label=OperatorFeedbackQualityLabel.WEAK,
            ),
        ]

        groups = PublishHealthService._group_outcomes(service, outcomes, lambda item: item.source_profile_name or "unknown")

        self.assertEqual(groups[0].label, "Food Page")
        self.assertEqual(groups[0].published_count, 1)
        self.assertEqual(groups[0].good_feedback_count, 1)
        self.assertEqual(groups[0].weak_feedback_count, 1)
        self.assertEqual(groups[0].needs_reconciliation_count, 1)
        self.assertEqual(groups[0].average_score, 80.0)


if __name__ == "__main__":
    unittest.main()
