from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.analytics.services.facebook_insights_live_pilot_service import (
    FacebookInsightsLivePilotService,
)
from src.analytics.services.publication_metric_collection_service import (
    PublicationMetricCollectionError,
    PublicationMetricCollectionService,
)
from src.enums import ExternalPublicationStatus, PlatformAccountStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PlatformPublication
from src.publish.services.platform_account_service import PlatformAccountService
from src.publish.services.platform_credential_store import PlatformCredentialStore
from src.schemas.analytics import FacebookInsightsLivePilotPreflightRequest


class _Session:
    def __init__(self, publication, account):
        self.publication = publication
        self.account = account

    def get(self, model, object_id):
        if model is PlatformPublication and object_id == self.publication.id:
            return self.publication
        if model is PlatformAccount and object_id == self.account.id:
            return self.account
        return None


def _request(publication, account) -> FacebookInsightsLivePilotPreflightRequest:
    return FacebookInsightsLivePilotPreflightRequest(
        operator_confirmation="FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
        expected_platform_account_id=account.id,
        expected_external_account_id=account.external_account_id,
        expected_media_id=publication.external_reel_id,
        required_scopes=["read_insights", "pages_read_engagement"],
    )


class FacebookInsightsLivePilotPreflightTests(unittest.TestCase):
    def _ready_authority(self):
        now = datetime.now(UTC)
        account = SimpleNamespace(
            id=uuid4(),
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            external_account_id="123456789012345",
            token_reference="FACEBOOK_PAGE_123_INSIGHTS_TOKEN",
            status=PlatformAccountStatus.ACTIVE,
            is_on_hold=False,
            cooldown_until=None,
            metadata_json={
                "metrics_insights_enabled": True,
                "facebook_insights_token_type": "PAGE_ACCESS_TOKEN",
                "facebook_insights_verified_external_account_id": "123456789012345",
                "facebook_verified_insights_scopes": [
                    "read_insights",
                    "pages_read_engagement",
                ],
                "facebook_insights_scopes_verified_at": now.isoformat(),
                "facebook_publish_capability_verified": True,
                "facebook_verified_publish_scopes": ["pages_show_list", "pages_manage_posts"],
                "facebook_page_tasks": ["CREATE_CONTENT", "ANALYZE"],
                "facebook_publish_capability_verified_at": now.isoformat(),
                "graph_api_version": "v20.0",
                "facebook_insights_object_id_source": "external_reel_id",
            },
        )
        publication = SimpleNamespace(
            id=uuid4(),
            platform_account_id=account.id,
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            status=ExternalPublicationStatus.PUBLISHED,
            external_publish_id="123456789012345_987654321098765",
            external_media_id="987654321098765",
            external_reel_id="987654321098765",
            external_permalink="https://www.facebook.com/reel/987654321098765",
            metadata_json={
                "facebook_insights_verified_media_id": "987654321098765",
                "facebook_insights_object_verified_at": now.isoformat(),
            },
        )
        return publication, account

    def test_fully_attested_authority_is_ready_without_network_or_token_resolution(self) -> None:
        publication, account = self._ready_authority()
        response = FacebookInsightsLivePilotService(
            _Session(publication, account)  # type: ignore[arg-type]
        ).preflight(publication.id, _request(publication, account))

        self.assertTrue(response.ready_for_live_job)
        self.assertFalse(response.network_used)
        self.assertTrue(response.token_resolution_deferred_to_worker)
        self.assertEqual(response.blocker_codes, [])
        self.assertTrue(all(item.passed for item in response.checks))

    def test_demo_authority_is_blocked_with_actionable_codes(self) -> None:
        publication, account = self._ready_authority()
        account.external_account_id = "fb-page-demo-food-main"
        account.metadata_json = {}
        account.token_reference = None
        publication.external_publish_id = "local-pilot-123"
        publication.external_media_id = "local-media-123"
        publication.external_reel_id = "local-reel-123"
        publication.external_permalink = "https://example.invalid/reel/local-reel-123"
        publication.metadata_json = {}

        response = FacebookInsightsLivePilotService(
            _Session(publication, account)  # type: ignore[arg-type]
        ).preflight(publication.id, _request(publication, account))

        self.assertFalse(response.ready_for_live_job)
        self.assertFalse(response.network_used)
        self.assertIn("production_account_identity", response.blocker_codes)
        self.assertIn("token_reference", response.blocker_codes)
        self.assertIn("verified_scopes", response.blocker_codes)
        self.assertIn("production_media_identity", response.blocker_codes)
        self.assertIn("facebook_permalink", response.blocker_codes)

    def test_oauth_managed_encrypted_credential_reference_is_ready(self) -> None:
        publication, account = self._ready_authority()
        account.token_reference = PlatformCredentialStore.reference_for(uuid4())

        response = FacebookInsightsLivePilotService(
            _Session(publication, account)  # type: ignore[arg-type]
        ).preflight(publication.id, _request(publication, account))

        self.assertTrue(response.ready_for_live_job)
        self.assertNotIn("token_reference", response.blocker_codes)

    def test_malformed_encrypted_credential_reference_is_blocked(self) -> None:
        publication, account = self._ready_authority()
        account.token_reference = "platform-credential://not-a-uuid"

        response = FacebookInsightsLivePilotService(
            _Session(publication, account)  # type: ignore[arg-type]
        ).preflight(publication.id, _request(publication, account))

        self.assertFalse(response.ready_for_live_job)
        self.assertIn("token_reference", response.blocker_codes)

    def test_stale_attestation_blocks_preflight_independently_of_scheduler(self) -> None:
        publication, account = self._ready_authority()
        stale = datetime.now(UTC) - timedelta(days=31)
        account.metadata_json["facebook_insights_scopes_verified_at"] = stale.isoformat()
        publication.metadata_json["facebook_insights_object_verified_at"] = stale.isoformat()

        response = FacebookInsightsLivePilotService(
            _Session(publication, account)  # type: ignore[arg-type]
        ).preflight(publication.id, _request(publication, account))

        self.assertIn("scope_verification_fresh", response.blocker_codes)
        self.assertIn("media_verification_fresh", response.blocker_codes)
        self.assertNotIn("scheduler_disabled", response.blocker_codes)

    def test_collection_boundary_enforces_preflight_and_fixture_bypass_is_explicit(self) -> None:
        publication, account = self._ready_authority()
        session = _Session(publication, account)
        account.metadata_json = {}
        with self.assertRaises(PublicationMetricCollectionError) as blocked:
            PublicationMetricCollectionService(
                session  # type: ignore[arg-type]
            )._assert_facebook_live_preflight("FACEBOOK_GRAPH", publication, account)
        self.assertEqual(blocked.exception.code, "metrics_live_preflight_required")

        PublicationMetricCollectionService(
            session,  # type: ignore[arg-type]
            enforce_facebook_live_preflight=False,
        )._assert_facebook_live_preflight("FACEBOOK_GRAPH", publication, account)

    def test_preflight_route_is_registered(self) -> None:
        from src.main import app

        path = "/platform-publications/{platform_publication_id}/facebook-insights-live-preflight"
        self.assertIn(path, app.openapi()["paths"])
        self.assertIn("post", app.openapi()["paths"][path])

    def test_account_setup_check_is_secret_safe_and_actionable(self) -> None:
        _publication, account = self._ready_authority()
        service = PlatformAccountService(_Session(_publication, account))  # type: ignore[arg-type]
        with patch.object(service, "_resolve_access_token", return_value="secret-token"):
            response = service.facebook_setup_check(account.id)

        self.assertTrue(response["ready_for_publication_setup"])
        self.assertFalse(response["network_used"])
        self.assertFalse(response["token_value_exposed"])
        self.assertNotIn("secret-token", str(response))

    def test_account_setup_route_is_registered(self) -> None:
        from src.main import app

        path = "/platform-accounts/{platform_account_id}/facebook-setup-check"
        self.assertIn(path, app.openapi()["paths"])
        self.assertIn("post", app.openapi()["paths"][path])

        import_path = "/platform-publications/manual-import"
        self.assertIn(import_path, app.openapi()["paths"])
        self.assertIn("post", app.openapi()["paths"][import_path])


if __name__ == "__main__":
    unittest.main()
