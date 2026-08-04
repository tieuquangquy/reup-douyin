from datetime import UTC, datetime, timedelta
import unittest
from uuid import uuid4

from src.core.settings import Settings
from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount
from src.schemas.publish import PlatformAccountUpdateRequest
from src.publish.services.platform_account_service import PlatformAccountError, PlatformAccountService
from src.publish.services.facebook_publish_safety_service import FacebookPublishSafetyService


class _SafetySession:
    def __init__(self, scalar_results: list[object] | None = None):
        self.scalar_results = list(scalar_results or [0, 0, 0, None, 0, 0])

    def scalar(self, _statement):
        if not self.scalar_results:
            raise AssertionError("Unexpected safety query")
        return self.scalar_results.pop(0)


class _AccountUpdateSession:
    def __init__(self, account: PlatformAccount):
        self.account = account

    def get(self, model, object_id):
        return self.account if object_id == self.account.id else None

    def commit(self):
        return None

    def rollback(self):
        return None

    def refresh(self, _account):
        return None


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://unused",
        "facebook_publish_guardrails_enabled": True,
        "facebook_publish_require_verified_capability": True,
    }
    values.update(overrides)
    return Settings(**values)


def _account(now: datetime) -> PlatformAccount:
    return PlatformAccount(
        id=uuid4(),
        workspace_id=uuid4(),
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        display_name="Safe Page",
        external_account_id="123456789",
        status=PlatformAccountStatus.ACTIVE,
        is_on_hold=False,
        metadata_json={
            "facebook_publish_capability_verified": True,
            "facebook_verified_publish_scopes": ["pages_manage_posts", "pages_show_list"],
            "facebook_page_tasks": ["CREATE_CONTENT", "ANALYZE"],
            "facebook_publish_capability_verified_at": now.isoformat(),
            "facebook_oauth_connected_at": now.isoformat(),
        },
    )


class FacebookPublishSafetyTests(unittest.TestCase):
    def test_verified_page_is_allowed_and_enters_warmup(self) -> None:
        now = datetime.now(UTC)
        db = _SafetySession()
        decision = FacebookPublishSafetyService(
            db,  # type: ignore[arg-type]
            settings=_settings(),
        ).evaluate(_account(now), now=now)

        self.assertTrue(decision.allowed)
        self.assertIn("pilot", " ".join(decision.warnings))
        self.assertFalse(db.scalar_results)

    def test_status_snapshot_is_secret_safe_and_actionable(self) -> None:
        now = datetime.now(UTC)
        status = FacebookPublishSafetyService(
            _SafetySession(),  # type: ignore[arg-type]
            settings=_settings(),
        ).status(_account(now), now=now)

        self.assertEqual(status["state"], "WARM_UP")
        self.assertEqual(status["warmup_stage"], "PILOT")
        self.assertEqual(status["next_stage_min_successes"], 2)
        self.assertTrue(status["eligible_for_publish"])
        self.assertEqual(status["verified_publish_scopes"], ["pages_manage_posts", "pages_show_list"])
        self.assertNotIn("token", repr(status).lower())

    def test_oauth_managed_identity_cannot_be_edited_through_generic_update(self) -> None:
        account = _account(datetime.now(UTC))
        account.token_reference = "platform-credential://managed"
        account.metadata_json = {
            **(account.metadata_json or {}),
            "credential_source": "META_OAUTH",
        }
        service = PlatformAccountService(
            _AccountUpdateSession(account),  # type: ignore[arg-type]
            settings=_settings(),
        )

        with self.assertRaises(PlatformAccountError):
            service.update_account(
                account.id,
                PlatformAccountUpdateRequest(display_name="Tampered Page"),
            )

    def test_missing_publish_capability_fails_closed(self) -> None:
        now = datetime.now(UTC)
        account = _account(now)
        account.metadata_json = {}
        decision = FacebookPublishSafetyService(
            _SafetySession(),  # type: ignore[arg-type]
            settings=_settings(),
        ).evaluate(account, now=now)

        self.assertFalse(decision.allowed)
        self.assertTrue(any("pages_manage_posts" in item for item in decision.reasons))
        self.assertTrue(any("CREATE_CONTENT" in item for item in decision.reasons))

    def test_warmup_attempt_budget_blocks_burst(self) -> None:
        now = datetime.now(UTC)
        db = _SafetySession([0, 0, 0, None, 2, 0])
        decision = FacebookPublishSafetyService(
            db,  # type: ignore[arg-type]
            settings=_settings(facebook_publish_warmup_max_attempts_per_24h=2),
        ).evaluate(_account(now), now=now)

        self.assertFalse(decision.allowed)
        self.assertTrue(any("24-hour attempt budget" in item for item in decision.reasons))

    def test_mature_page_requires_confirmed_connector_successes_for_standard_stage(self) -> None:
        now = datetime.now(UTC)
        account = _account(now - timedelta(days=10))
        account.metadata_json["facebook_oauth_connected_at"] = (now - timedelta(days=10)).isoformat()
        status = FacebookPublishSafetyService(
            _SafetySession([5, 0, 0, None, 0, 0]),  # type: ignore[arg-type]
            settings=_settings(),
        ).status(account, now=now)

        self.assertEqual(status["warmup_stage"], "STANDARD")
        self.assertEqual(status["state"], "READY")

    def test_rate_limit_applies_cooldown_and_auth_error_applies_hold(self) -> None:
        now = datetime.now(UTC)
        service = FacebookPublishSafetyService(
            _SafetySession(),  # type: ignore[arg-type]
            settings=_settings(facebook_publish_rate_limit_cooldown_minutes=180),
        )
        account = _account(now - timedelta(days=10))

        service.apply_connector_failure(account, error_code="facebook_rate_limited", now=now)
        self.assertGreaterEqual(account.cooldown_until, now + timedelta(minutes=180))
        self.assertEqual(account.status, PlatformAccountStatus.ACTIVE)

        service.apply_connector_failure(account, error_code="facebook_token_invalid", now=now)
        self.assertEqual(account.status, PlatformAccountStatus.PAUSED)
        self.assertTrue(account.is_on_hold)
        self.assertIn("FACEBOOK_SAFETY_HOLD", account.hold_reason or "")


if __name__ == "__main__":
    unittest.main()
