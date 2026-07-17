from datetime import UTC, datetime
import unittest

from src.services.capture_metadata_normalizer import CaptureMetadataNormalizeInput, CaptureMetadataNormalizer


class CaptureMetadataNormalizerTests(unittest.TestCase):
    def test_network_create_time_normalizes_posted_at(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme={"create_time": 1710000000},
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertIsNotNone(result.posted_at)
        self.assertEqual(result.posted_source, "network_json")

    def test_detail_create_time_fallback(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme={"create_time": 1710000001},
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertIsNotNone(result.posted_at)
        self.assertEqual(result.posted_source, "detail_hydrate")

    def test_invalid_numeric_posted_text_rejected(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme=None,
                raw_dom_snapshot={"visible_text": "13.0"},
                raw_evidence_summary=None,
            )
        )

        self.assertIsNone(result.posted_text)
        self.assertEqual(result.time_status, "missing")

    def test_network_duration_ms_to_seconds(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme={"video": {"duration": 83000}},
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.duration_seconds, 83.0)
        self.assertEqual(result.duration_text, "01:23")
        self.assertEqual(result.duration_source, "network_json")

    def test_detail_duration_fallback(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme={"video": {"duration": 42000}},
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.duration_seconds, 42.0)
        self.assertEqual(result.duration_source, "detail_hydrate")

    def test_invalid_duration_rejected(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme={"video": {"duration": "invalid"}},
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertIsNone(result.duration_seconds)
        self.assertEqual(result.processing_fit_status, "missing")

    def test_network_statistics_counts(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme={"statistics": {"play_count": 100, "digg_count": 20, "comment_count": 5, "share_count": 2}},
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.view_count, 100)
        self.assertEqual(result.like_count, 20)
        self.assertEqual(result.comment_count, 5)
        self.assertEqual(result.share_count, 2)
        self.assertEqual(result.performance_status, "captured")

    def test_detail_statistics_fallback(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme={"statistics": {"play_count": 12, "digg_count": 3}},
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.view_count, 12)
        self.assertEqual(result.like_count, 3)
        self.assertEqual(result.view_count_source, "detail_hydrate")

    def test_negative_statistics_rejected(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme={"statistics": {"play_count": -1, "digg_count": -2}},
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertIsNone(result.view_count)
        self.assertEqual(result.performance_status, "missing")

    def test_engagement_rate_derived_when_trustworthy(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme={"statistics": {"play_count": 100, "digg_count": 10, "comment_count": 5, "share_count": 5}},
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.engagement_rate, 0.2)

    def test_missing_evidence_sets_missing_reasons(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.metadata_status, "missing")
        self.assertEqual(result.time_missing_reason, "no_network_or_detail_evidence")
        self.assertEqual(result.performance_missing_reason, "no_network_or_detail_evidence")
        self.assertEqual(result.processing_fit_missing_reason, "no_network_or_detail_evidence")

    def test_dom_detail_modal_duration_and_counts_are_used_as_fallback(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_dom_detail_metrics={
                    "duration_seconds": 619,
                    "duration_text": "10:19",
                    "like_count": 197,
                    "comment_count": 10,
                    "share_count": 1,
                    "posted_text": "18小时前",
                    "extraction_source": "dom_detail_modal",
                    "confidence": "high",
                },
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.duration_seconds, 619)
        self.assertEqual(result.duration_source, "dom_detail_modal")
        self.assertEqual(result.like_count, 197)
        self.assertEqual(result.comment_count, 10)
        self.assertEqual(result.share_count, 1)
        self.assertEqual(result.like_count_source, "dom_detail_modal")
        self.assertEqual(result.posted_text, "18小时前")
        self.assertEqual(result.posted_source, "dom_detail_modal")
        self.assertIsNone(result.view_count)

    def test_dom_detail_zero_sentinel_text_recovers_zero_counts(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_dom_detail_metrics={
                    "like_count": 12,
                    "comment_count_text": "抢首评",
                    "share_count_text": "分享",
                    "extraction_source": "dom_detail_modal",
                    "confidence": "high",
                },
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.comment_count, 0)
        self.assertEqual(result.share_count, 0)
        self.assertEqual(result.comment_count_source, "dom_zero_sentinel")
        self.assertEqual(result.share_count_source, "dom_zero_sentinel")

    def test_calibrated_point_dom_duration_and_counts_are_accepted_as_dom_detail_fallback(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_dom_detail_metrics={
                    "duration_seconds": 671.94,
                    "like_count": 684,
                    "comment_count": 46,
                    "favorite_count": 151,
                    "share_count": 90,
                    "extraction_source": "calibrated_point_dom",
                    "confidence": "high",
                },
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.duration_seconds, 671.94)
        self.assertEqual(result.like_count, 684)
        self.assertEqual(result.comment_count, 46)
        self.assertEqual(result.share_count, 90)
        self.assertEqual(result.performance_status, "captured")
        self.assertEqual(result.processing_fit_status, "captured")
        self.assertEqual(result.duration_source, "dom_detail_modal")
        self.assertEqual(result.like_count_source, "dom_detail_modal")

    def test_profile_card_like_fallback_source_is_preserved(self) -> None:
        result = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=None,
                raw_detail_aweme=None,
                raw_dom_snapshot=None,
                raw_dom_detail_metrics={
                    "like_count": 392,
                    "like_count_text": "392",
                    "like_count_source": "dom_profile_card_fallback",
                    "extraction_source": "dom_detail_modal",
                    "confidence": "high",
                },
                raw_evidence_summary=None,
            )
        )

        self.assertEqual(result.like_count, 392)
        self.assertEqual(result.like_count_source, "dom_profile_card_fallback")
        self.assertEqual(result.performance_status, "captured")


if __name__ == "__main__":
    unittest.main()
