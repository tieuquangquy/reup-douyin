from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse
import unittest
from uuid import uuid4

from src.core.settings import Settings
from src.enums import PlatformAccountStatus
from src.models.publish import PlatformAccount, PlatformCredential, PlatformIntegrationConfiguration, PlatformOAuthSession
from src.publish.services.facebook_oauth_service import FacebookOAuthError, FacebookOAuthService
from src.publish.services.platform_credential_key_store import resolve_platform_credential_key_ref
from src.publish.services.platform_secret_envelope import PlatformSecretEnvelope


class _FakeTransport:
    def exchange_code(self, code: str) -> str:
        assert code == "oauth-code"
        return "SHORT_USER_TOKEN"

    def exchange_long_lived_user_token(self, short_lived_token: str) -> str:
        assert short_lived_token == "SHORT_USER_TOKEN"
        return "LONG_USER_TOKEN"

    def fetch_granted_scopes(self, user_token: str) -> set[str]:
        assert user_token == "LONG_USER_TOKEN"
        return {"pages_show_list", "pages_read_engagement", "read_insights", "pages_manage_posts"}

    def fetch_pages(self, user_token: str) -> list[dict]:
        assert user_token == "LONG_USER_TOKEN"
        return [
            {
                "id": "123456789",
                "name": "My Facebook Page",
                "access_token": "PAGE_TOKEN_MUST_STAY_SERVER_SIDE",
                "tasks": ["CREATE_CONTENT", "ANALYZE"],
                "picture": {"data": {"url": "https://cdn.example.test/page-avatar.jpg"}},
            }
        ]


class _MissingPublishCapabilityTransport(_FakeTransport):
    def fetch_granted_scopes(self, user_token: str) -> set[str]:
        assert user_token == "LONG_USER_TOKEN"
        return {"pages_show_list", "pages_read_engagement", "read_insights"}

    def fetch_pages(self, user_token: str) -> list[dict]:
        rows = super().fetch_pages(user_token)
        rows[0]["tasks"] = ["ANALYZE"]
        return rows


class _MultiplePagesTransport(_FakeTransport):
    def fetch_pages(self, user_token: str) -> list[dict]:
        rows = super().fetch_pages(user_token)
        rows.append(
            {
                "id": "987654321",
                "name": "Second Facebook Page",
                "access_token": "SECOND_PAGE_TOKEN_MUST_STAY_SERVER_SIDE",
                "tasks": ["CREATE_CONTENT", "ANALYZE"],
            }
        )
        return rows


class _FakeSession:
    def __init__(self):
        self.oauth_sessions: list[PlatformOAuthSession] = []
        self.accounts: list[PlatformAccount] = []
        self.credentials: list[PlatformCredential] = []
        self.integration_configurations: list[PlatformIntegrationConfiguration] = []

    def add(self, row):
        if isinstance(row, PlatformOAuthSession):
            self.oauth_sessions.append(row)
        elif isinstance(row, PlatformAccount):
            self.accounts.append(row)
        elif isinstance(row, PlatformCredential):
            self.credentials.append(row)
        elif isinstance(row, PlatformIntegrationConfiguration):
            self.integration_configurations.append(row)

    def scalar(self, statement):
        sql = str(statement)
        if "FROM platform_oauth_sessions" in sql:
            return self.oauth_sessions[0] if self.oauth_sessions else None
        if "FROM platform_accounts" in sql:
            # The fake session does not interpolate SQL bind values; OAuth
            # onboarding tests only use this lookup for account creation.
            return None
        if "FROM platform_credentials" in sql:
            return None
        if "FROM platform_integration_configurations" in sql:
            return self.integration_configurations[0] if self.integration_configurations else None
        raise AssertionError(sql)

    def get(self, model, object_id):
        collection = {
            PlatformOAuthSession: self.oauth_sessions,
            PlatformAccount: self.accounts,
            PlatformCredential: self.credentials,
            PlatformIntegrationConfiguration: self.integration_configurations,
        }.get(model, [])
        return next((row for row in collection if row.id == object_id), None)

    def flush(self):
        now = datetime.now(UTC)
        for row in [*self.oauth_sessions, *self.accounts, *self.credentials, *self.integration_configurations]:
            if getattr(row, "created_at", None) is None:
                row.created_at = now
            if getattr(row, "updated_at", None) is None:
                row.updated_at = now

    def commit(self):
        self.flush()

    def rollback(self):
        return None

    def refresh(self, _row):
        return None


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://unused",
        "facebook_app_id": "meta-app-id",
        "facebook_app_secret": "meta-app-secret",
        "facebook_oauth_redirect_uri": "http://localhost:3000/publishing/accounts",
        "facebook_graph_api_version": "v20.0",
        "platform_credential_encryption_key_ref": "this-local-test-passphrase-is-at-least-32-bytes",
    }
    values.update(overrides)
    return Settings(**values)


class FacebookOAuthOnboardingTests(unittest.TestCase):
    def test_local_key_store_bootstraps_once_without_env_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            key_path = Path(directory) / "platform.key"
            settings = _settings(
                platform_credential_encryption_key_ref=None,
                platform_credential_local_key_path=str(key_path),
            )
            generated = resolve_platform_credential_key_ref(settings, create_local=True)
            resolved = resolve_platform_credential_key_ref(settings)

            self.assertTrue(key_path.exists())
            self.assertEqual(resolved, generated)
            self.assertTrue(str(generated).startswith("base64:"))

    def test_platform_envelope_is_context_bound_and_not_plaintext(self) -> None:
        envelope = PlatformSecretEnvelope(key_ref="this-local-test-passphrase-is-at-least-32-bytes")
        encrypted = envelope.encrypt("top-secret", context="credential:one")
        self.assertNotIn("top-secret", encrypted)
        self.assertEqual(envelope.decrypt(encrypted, context="credential:one"), "top-secret")
        self.assertIsNone(envelope.decrypt(encrypted, context="credential:two"))

    def test_configuration_fails_closed_without_meta_or_encryption_settings(self) -> None:
        with TemporaryDirectory() as directory:
            db = _FakeSession()
            service = FacebookOAuthService(
                db,  # type: ignore[arg-type]
                settings=_settings(
                    facebook_app_id=None,
                    facebook_app_secret=None,
                    platform_credential_encryption_key_ref=None,
                    platform_credential_local_key_path=str(Path(directory) / "missing.key"),
                ),
                transport=_FakeTransport(),
            )
            config = service.configuration()
            self.assertFalse(config["configured"])
            self.assertIn("FACEBOOK_APP_ID", config["missing_configuration"])
            self.assertIn("FACEBOOK_APP_SECRET", config["missing_configuration"])
            self.assertIn("PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF", config["missing_configuration"])
            with self.assertRaises(FacebookOAuthError) as raised:
                service.start(workspace_id=uuid4(), subject="operator-1")
            self.assertEqual(raised.exception.code, "facebook_oauth_not_configured")

    def test_configuration_rejects_permission_inflation(self) -> None:
        service = FacebookOAuthService(
            _FakeSession(),  # type: ignore[arg-type]
            settings=_settings(
                facebook_oauth_scopes=(
                    "pages_show_list,pages_manage_posts,pages_messaging"
                )
            ),
            transport=_FakeTransport(),
        )

        config = service.configuration()

        self.assertFalse(config["configured"])
        self.assertIn("FACEBOOK_OAUTH_SCOPES", config["missing_configuration"])

    def test_workspace_configuration_encrypts_app_secret_and_overrides_environment(self) -> None:
        db = _FakeSession()
        workspace_id = uuid4()
        service = FacebookOAuthService(
            db,  # type: ignore[arg-type]
            settings=_settings(),
            transport=_FakeTransport(),
        )

        saved = service.save_configuration(
            workspace_id=workspace_id,
            subject="owner-1",
            app_id="123456789012345",
            app_secret="DATABASE_APP_SECRET_MUST_NOT_LEAK",
            redirect_uri="http://localhost:3000/publishing/accounts",
            graph_api_version="v21.0",
            requested_scopes=[
                "pages_show_list",
                "pages_read_engagement",
                "read_insights",
                "pages_manage_posts",
            ],
        )

        self.assertEqual(saved["source"], "DATABASE")
        self.assertEqual(saved["app_id"], "123456789012345")
        self.assertTrue(saved["app_secret_configured"])
        self.assertNotIn("DATABASE_APP_SECRET_MUST_NOT_LEAK", repr(saved))
        self.assertEqual(len(db.integration_configurations), 1)
        self.assertNotIn(
            "DATABASE_APP_SECRET_MUST_NOT_LEAK",
            db.integration_configurations[0].encrypted_app_secret,
        )
        encrypted_before_update = db.integration_configurations[0].encrypted_app_secret
        updated = service.save_configuration(
            workspace_id=workspace_id,
            subject="owner-1",
            app_id="123456789012345",
            app_secret=None,
            redirect_uri="http://localhost:3000/publishing/accounts",
            graph_api_version="v21.0",
            requested_scopes=["pages_show_list", "pages_manage_posts"],
        )
        self.assertEqual(db.integration_configurations[0].encrypted_app_secret, encrypted_before_update)
        self.assertTrue(updated["app_secret_configured"])
        started = service.start(workspace_id=workspace_id, subject="owner-1")
        query = parse_qs(urlparse(started["authorization_url"]).query)
        self.assertEqual(query["client_id"], ["123456789012345"])
        self.assertIn("/v21.0/dialog/oauth", started["authorization_url"])

    def test_oauth_discovers_page_and_stores_only_encrypted_page_token(self) -> None:
        db = _FakeSession()
        workspace_id = uuid4()
        service = FacebookOAuthService(
            db,  # type: ignore[arg-type]
            settings=_settings(),
            transport=_FakeTransport(),
        )

        started = service.start(workspace_id=workspace_id, subject="operator-1")
        query = parse_qs(urlparse(started["authorization_url"]).query)
        self.assertEqual(query["client_id"], ["meta-app-id"])
        self.assertNotIn("meta-app-secret", started["authorization_url"])
        state = query["state"][0]

        callback = service.complete_callback(
            workspace_id=workspace_id,
            subject="operator-1",
            state=state,
            code="oauth-code",
        )
        self.assertEqual(callback["status"], "PAGE_SELECTION_REQUIRED")
        self.assertEqual(callback["pages"], [{"page_id": "123456789", "display_name": "My Facebook Page", "tasks": ["ANALYZE", "CREATE_CONTENT"], "picture_url": "https://cdn.example.test/page-avatar.jpg"}])
        self.assertNotIn("PAGE_TOKEN", repr(callback))
        self.assertNotIn("PAGE_TOKEN_MUST_STAY_SERVER_SIDE", db.oauth_sessions[0].encrypted_payload or "")

        connected = service.connect_page(
            started["connection_id"],
            workspace_id=workspace_id,
            subject="operator-1",
            page_id="123456789",
            priority=100,
        )
        account = connected["account"]
        self.assertTrue(connected["created"])
        self.assertTrue(connected["setup_check"]["ready_for_publication_setup"])
        self.assertTrue(account.token_reference.startswith("platform-credential://"))
        self.assertEqual(account.metadata_json["facebook_page_picture_url"], "https://cdn.example.test/page-avatar.jpg")
        self.assertEqual(len(db.credentials), 1)
        self.assertNotIn("PAGE_TOKEN_MUST_STAY_SERVER_SIDE", db.credentials[0].encrypted_value)
        self.assertEqual(db.oauth_sessions[0].status, "COMPLETED")
        self.assertIsNone(db.oauth_sessions[0].encrypted_payload)

    def test_one_oauth_session_can_connect_multiple_pages(self) -> None:
        db = _FakeSession()
        workspace_id = uuid4()
        service = FacebookOAuthService(
            db,  # type: ignore[arg-type]
            settings=_settings(),
            transport=_MultiplePagesTransport(),
        )
        started = service.start(workspace_id=workspace_id, subject="operator-1")
        state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
        callback = service.complete_callback(
            workspace_id=workspace_id,
            subject="operator-1",
            state=state,
            code="oauth-code",
        )
        self.assertEqual(len(callback["pages"]), 2)

        service.connect_page(
            started["connection_id"],
            workspace_id=workspace_id,
            subject="operator-1",
            page_id="123456789",
            priority=80,
        )
        remaining = service.get_session(
            started["connection_id"],
            workspace_id=workspace_id,
            subject="operator-1",
        )
        self.assertEqual(remaining["status"], "PAGE_SELECTION_REQUIRED")
        self.assertEqual([item["page_id"] for item in remaining["pages"]], ["987654321"])
        self.assertNotIn("SECOND_PAGE_TOKEN_MUST_STAY_SERVER_SIDE", repr(remaining))

        service.connect_page(
            started["connection_id"],
            workspace_id=workspace_id,
            subject="operator-1",
            page_id="987654321",
            priority=80,
        )
        self.assertEqual(len(db.accounts), 2)
        self.assertEqual(len(db.credentials), 2)
        self.assertEqual(db.oauth_sessions[0].status, "COMPLETED")
        self.assertIsNone(db.oauth_sessions[0].encrypted_payload)
        self.assertEqual(
            db.oauth_sessions[0].metadata_json["connected_page_ids"],
            ["123456789", "987654321"],
        )

    def test_state_is_bound_to_operator_and_cannot_be_replayed(self) -> None:
        db = _FakeSession()
        workspace_id = uuid4()
        service = FacebookOAuthService(db, settings=_settings(), transport=_FakeTransport())  # type: ignore[arg-type]
        started = service.start(workspace_id=workspace_id, subject="operator-1")
        state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
        with self.assertRaises(FacebookOAuthError) as wrong_operator:
            service.complete_callback(
                workspace_id=workspace_id,
                subject="operator-2",
                state=state,
                code="oauth-code",
            )
        self.assertEqual(wrong_operator.exception.code, "facebook_oauth_state_invalid")

        service.complete_callback(
            workspace_id=workspace_id,
            subject="operator-1",
            state=state,
            code="oauth-code",
        )
        with self.assertRaises(FacebookOAuthError) as replayed:
            service.complete_callback(
                workspace_id=workspace_id,
                subject="operator-1",
                state=state,
                code="oauth-code",
            )
        self.assertEqual(replayed.exception.code, "facebook_oauth_state_replayed")

    def test_page_without_publish_capability_is_connected_on_safety_hold(self) -> None:
        db = _FakeSession()
        workspace_id = uuid4()
        service = FacebookOAuthService(
            db,  # type: ignore[arg-type]
            settings=_settings(),
            transport=_MissingPublishCapabilityTransport(),
        )
        started = service.start(workspace_id=workspace_id, subject="operator-1")
        state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
        service.complete_callback(
            workspace_id=workspace_id,
            subject="operator-1",
            state=state,
            code="oauth-code",
        )

        connected = service.connect_page(
            started["connection_id"],
            workspace_id=workspace_id,
            subject="operator-1",
            page_id="123456789",
            priority=100,
        )

        account = connected["account"]
        self.assertEqual(account.status, PlatformAccountStatus.PAUSED)
        self.assertTrue(account.is_on_hold)
        self.assertFalse(connected["setup_check"]["ready_for_publication_setup"])
        self.assertIn("publish_scope", connected["setup_check"]["blocker_codes"])
        self.assertIn("publish_page_task", connected["setup_check"]["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
