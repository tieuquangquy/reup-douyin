from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError

from src.analytics.collectors.base import MetricCollectorError
from src.analytics.collectors.facebook_reels_insights import (
    DEFAULT_FACEBOOK_VIDEO_INSIGHT_METRICS,
    FacebookInsightsTransport,
    FacebookReelsInsightsCollector,
    normalize_facebook_video_insights,
)
from src.analytics.services.publication_metric_collection_service import (
    PublicationMetricCollectionError,
    PublicationMetricCollectionService,
)
from src.enums import PublishTargetPlatform
from src.publish.types import PlatformAccountConfig
from src.schemas.analytics import (
    PublicationMetricCollectionEnqueueRequest,
    PublicationMetricMockPayload,
    PublicationMetricScheduleUpsertRequest,
)


FIXTURE = {
    "data": [
        {"name": "total_video_views", "period": "lifetime", "values": [{"value": 1000}]},
        {"name": "total_video_view_time", "period": "lifetime", "values": [{"value": 120000}]},
        {"name": "total_video_complete_views", "period": "lifetime", "values": [{"value": 600}]},
        {
            "name": "total_video_reactions_by_type_total",
            "period": "lifetime",
            "values": [{"value": {"like": 80, "love": 5}}],
        },
        {"name": "comment_count", "values": [{"value": 10}]},
        {"name": "share_count", "values": [{"value": 5}]},
    ]
}


class _FixtureTransport:
    def __init__(self, payload=None):
        self.payload = payload or FIXTURE
        self.calls = []

    def fetch_video_insights(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload

    def fetch_video_counters(self, **kwargs):
        self.calls.append({"counter_request": kwargs})
        return {
            "id": "reel-1",
            "views": 1000,
            "likes": {"summary": {"total_count": 80}},
            "comments": {"summary": {"total_count": 10}},
        }


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return self.body


class FacebookInsightsNormalizationTests(unittest.TestCase):
    def test_default_metrics_use_graph_v26_compatible_view_time_name(self) -> None:
        self.assertIn("post_video_view_time", DEFAULT_FACEBOOK_VIDEO_INSIGHT_METRICS)
        self.assertNotIn("total_video_view_time", DEFAULT_FACEBOOK_VIDEO_INSIGHT_METRICS)

    def test_normalizes_lifetime_metrics_without_inventing_missing_values(self) -> None:
        requested = [
            "total_video_views",
            "total_video_view_time",
            "total_video_complete_views",
            "total_video_reactions_by_type_total",
            "comment_count",
            "share_count",
        ]
        result = normalize_facebook_video_insights(FIXTURE, requested_metrics=requested)

        self.assertEqual(result["view_count"], 1000)
        self.assertEqual(result["total_watch_time_seconds"], 120.0)
        self.assertEqual(result["completion_rate_percent"], 60.0)
        self.assertEqual(result["like_count"], 80)
        self.assertEqual(result["comment_count"], 10)
        self.assertEqual(result["share_count"], 5)
        self.assertEqual(result["unavailable_metrics"], [])
        self.assertEqual(result["data_quality"], "COMPLETE")

    def test_missing_requested_metric_is_reported_as_partial(self) -> None:
        result = normalize_facebook_video_insights(
            {"data": [{"name": "total_video_views", "values": [{"value": 100}]}]},
            requested_metrics=["total_video_views", "comment_count"],
        )
        self.assertIsNone(result["comment_count"])
        self.assertEqual(result["unavailable_metrics"], ["comment_count"])
        self.assertEqual(result["data_quality"], "PARTIAL")

    def test_object_counters_supply_reel_views_likes_and_comments(self) -> None:
        result = normalize_facebook_video_insights(
            {"data": [{"name": "post_video_view_time", "values": [{"value": 120000}]}]},
            requested_metrics=["total_video_views", "post_video_view_time"],
            counter_payload={
                "views": 1234,
                "likes": {"summary": {"total_count": 45}},
                "comments": {"summary": {"total_count": 6}},
            },
        )
        self.assertEqual(result["view_count"], 1234)
        self.assertEqual(result["like_count"], 45)
        self.assertEqual(result["comment_count"], 6)
        self.assertNotIn("total_video_views", result["unavailable_metrics"])
        self.assertIn("object.views", result["returned_metrics"])

    def test_non_data_payload_fails_closed(self) -> None:
        with self.assertRaises(MetricCollectorError) as context:
            normalize_facebook_video_insights({}, requested_metrics=["total_video_views"])
        self.assertEqual(context.exception.code, "metrics_provider_payload_invalid")


class FacebookInsightsCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.account = PlatformAccountConfig(
            platform_account_id=uuid4(),
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            page_id="page-1",
            display_name="Fixture Page",
            access_token="super-secret-token",
            graph_api_version="v20.0",
        )

    def test_collector_uses_configured_reference_and_allowlisted_metrics(self) -> None:
        transport = _FixtureTransport()
        collector = FacebookReelsInsightsCollector(transport=transport)  # type: ignore[arg-type]

        result = collector.collect(
            platform_publication_id=uuid4(),
            platform_account_id=self.account.platform_account_id,
            external_publish_id="publish-1",
            external_media_id="media-1",
            external_reel_id="reel-1",
            account_config=self.account,
            collector_config={
                "facebook_insights_object_id_source": "external_reel_id",
                "facebook_insights_metrics": [
                    "total_video_views",
                    "total_video_view_time",
                    "total_video_complete_views",
                    "not_allowlisted",
                ],
            },
            payload={},
        )

        self.assertEqual(transport.calls[0]["media_id"], "reel-1")
        self.assertNotIn("not_allowlisted", transport.calls[0]["metric_names"])
        self.assertEqual(result.view_count, 1000)
        self.assertNotIn("super-secret-token", str(result.provider_summary))
        self.assertTrue(result.provider_summary["network_used"])

    def test_transport_keeps_token_out_of_url(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["authorization"] = req.get_header("Authorization")
            captured["timeout"] = timeout
            return _Response(b'{"data": []}')

        with patch(
            "src.analytics.collectors.facebook_reels_insights.request.urlopen",
            side_effect=fake_urlopen,
        ):
            FacebookInsightsTransport().fetch_video_insights(
                account=self.account,
                media_id="media-1",
                metric_names=["total_video_views"],
            )

        self.assertNotIn("super-secret-token", captured["url"])
        self.assertEqual(captured["authorization"], "Bearer super-secret-token")

    def test_invalid_graph_version_fails_before_transport(self) -> None:
        invalid_account = PlatformAccountConfig(
            platform_account_id=self.account.platform_account_id,
            platform=self.account.platform,
            page_id=self.account.page_id,
            display_name=self.account.display_name,
            access_token=self.account.access_token,
            graph_api_version="v20.0/unsafe",
        )
        with (
            patch("src.analytics.collectors.facebook_reels_insights.request.urlopen") as urlopen,
            self.assertRaises(MetricCollectorError) as context,
        ):
            FacebookInsightsTransport().fetch_video_insights(
                account=invalid_account,
                media_id="media-1",
                metric_names=["total_video_views"],
            )
        self.assertEqual(context.exception.code, "metrics_configuration_invalid")
        urlopen.assert_not_called()

    def test_invalid_object_source_and_time_unit_fail_closed(self) -> None:
        collector = FacebookReelsInsightsCollector(transport=_FixtureTransport())  # type: ignore[arg-type]
        common = {
            "platform_publication_id": uuid4(),
            "platform_account_id": self.account.platform_account_id,
            "external_publish_id": "publish-1",
            "external_media_id": "media-1",
            "external_reel_id": "reel-1",
            "account_config": self.account,
            "payload": {},
        }
        with self.assertRaises(MetricCollectorError) as invalid_source:
            collector.collect(
                **common,
                collector_config={"facebook_insights_object_id_source": "typo"},
            )
        self.assertEqual(invalid_source.exception.code, "metrics_configuration_invalid")

        with self.assertRaises(MetricCollectorError) as invalid_unit:
            collector.collect(
                **common,
                collector_config={"facebook_view_time_unit": "minutes"},
            )
        self.assertEqual(invalid_unit.exception.code, "metrics_configuration_invalid")

    def test_graph_rate_limit_preserves_retry_after_without_raw_error(self) -> None:
        payload = {
            "error": {
                "code": 4,
                "error_subcode": 99,
                "message": "secret provider text must not be persisted",
            }
        }
        with self.assertRaises(MetricCollectorError) as context:
            FacebookInsightsTransport._raise_graph_error(
                payload,
                http_status=429,
                headers={"Retry-After": "600"},
            )
        error = context.exception
        self.assertEqual(error.code, "metrics_rate_limited")
        self.assertEqual(error.retry_after_seconds, 600)
        self.assertNotIn("secret provider text", str(error.provider_summary))
        self.assertEqual(error.provider_summary["graph_error_code"], 4)

    def test_auth_error_is_terminal(self) -> None:
        with self.assertRaises(MetricCollectorError) as context:
            FacebookInsightsTransport._raise_graph_error(
                {"error": {"code": 190}},
                http_status=400,
                headers=None,
            )
        self.assertEqual(context.exception.code, "metrics_auth_or_permission_denied")
        self.assertFalse(context.exception.retryable)

    def test_graph_code_100_distinguishes_bad_metric_from_missing_object(self) -> None:
        with self.assertRaises(MetricCollectorError) as invalid_metric:
            FacebookInsightsTransport._raise_graph_error(
                {"error": {"code": 100, "message": "The value must be a valid insights metric"}},
                http_status=400,
                headers=None,
            )
        self.assertEqual(invalid_metric.exception.code, "metrics_provider_request_invalid")

        with self.assertRaises(MetricCollectorError) as missing_object:
            FacebookInsightsTransport._raise_graph_error(
                {"error": {"code": 100, "message": "Unsupported get request. Object with ID does not exist"}},
                http_status=400,
                headers=None,
            )
        self.assertEqual(missing_object.exception.code, "metrics_media_not_found")


class FacebookInsightsGuardTests(unittest.TestCase):
    def _account(self, *, enabled: bool):
        return SimpleNamespace(
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            external_account_id="page-1",
            token_reference="FACEBOOK_PAGE_1_ACCESS_TOKEN",
            metadata_json={"metrics_insights_enabled": enabled},
        )

    def test_network_authorization_and_account_capability_are_both_required(self) -> None:
        with self.assertRaises(PublicationMetricCollectionError) as missing_network:
            PublicationMetricCollectionService._validate_collector_allowed(
                "FACEBOOK_GRAPH",
                external_network_authorized=False,
                account=self._account(enabled=True),
            )
        self.assertEqual(
            missing_network.exception.code,
            "metrics_external_network_authorization_required",
        )

        with self.assertRaises(PublicationMetricCollectionError) as missing_capability:
            PublicationMetricCollectionService._validate_collector_allowed(
                "FACEBOOK_GRAPH",
                external_network_authorized=True,
                account=self._account(enabled=False),
            )
        self.assertEqual(
            missing_capability.exception.code,
            "metrics_insights_capability_not_enabled",
        )

        PublicationMetricCollectionService._validate_collector_allowed(
            "FACEBOOK_GRAPH",
            external_network_authorized=True,
            account=self._account(enabled=True),
        )

    def test_exact_account_identity_and_token_reference_are_required(self) -> None:
        account = self._account(enabled=True)
        account.external_account_id = ""
        with self.assertRaises(PublicationMetricCollectionError) as missing_identity:
            PublicationMetricCollectionService._validate_collector_allowed(
                "FACEBOOK_GRAPH",
                external_network_authorized=True,
                account=account,
            )
        self.assertEqual(missing_identity.exception.code, "metrics_account_identity_missing")

        account.external_account_id = "page-1"
        account.token_reference = None
        with self.assertRaises(PublicationMetricCollectionError) as missing_reference:
            PublicationMetricCollectionService._validate_collector_allowed(
                "FACEBOOK_GRAPH",
                external_network_authorized=True,
                account=account,
            )
        self.assertEqual(
            missing_reference.exception.code,
            "metrics_account_credentials_reference_missing",
        )

    def test_schema_keeps_mock_and_facebook_payloads_separate(self) -> None:
        facebook = PublicationMetricCollectionEnqueueRequest(
            collection_key="facebook-slot-1",
            collector="FACEBOOK_GRAPH",
            external_network_authorized=True,
        )
        self.assertIsNone(facebook.mock_metrics)
        with self.assertRaises(ValidationError):
            PublicationMetricCollectionEnqueueRequest(
                collection_key="facebook-slot-2",
                collector="FACEBOOK_GRAPH",
                external_network_authorized=True,
                mock_metrics=PublicationMetricMockPayload(view_count=1),
            )
        schedule = PublicationMetricScheduleUpsertRequest(
            collector="FACEBOOK_GRAPH",
            external_network_authorized=True,
            operator_confirmation="FACEBOOK_INSIGHTS_AUTO_TRACKING_APPROVED",
        )
        self.assertIsNone(schedule.mock_growth_per_hour)


if __name__ == "__main__":
    unittest.main()
