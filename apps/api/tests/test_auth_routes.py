"""Phase A–C auth: operators, refresh, rate-limit, membership, invites."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_AUTH_REQUIRED", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-thirty-two-characters")
os.environ.setdefault("JWT_ISSUER", "reup-douyin-test")
os.environ.setdefault("JWT_AUDIENCE", "reup-douyin-web-test")
os.environ.setdefault("JWT_API_AUDIENCE", "reup-douyin-api-test")
os.environ.setdefault("JWT_OPS_AUDIENCE", "reup-douyin-ops-test")
os.environ["AUTH_REGISTRATION_ENABLED"] = "true"
os.environ["AUTH_ACCESS_TOKEN_TTL_MINUTES"] = "30"
os.environ["AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "100"

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite cannot native-create PostgreSQL JSONB; compile as JSON for auth unit DB.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[no-untyped-def]
    return "TEXT"


from fastapi.testclient import TestClient

from src.core.settings import get_settings
from src.db.base import Base
from src.db.bootstrap import ensure_default_workspace
from src.db.session import get_db_session, get_engine
from src.main import create_app
from src.models.auth_session import OperatorInvite, OperatorRefreshToken, WorkspaceMembership
from src.models.foundation import Workspace
from src.models.operators import Operator
from src.services.auth_rate_limit import auth_rate_limiter
from src.services.password_hashing import hash_password, verify_password
import src.models  # noqa: F401


_AUTH_TABLES = [
    Workspace.__table__,
    Operator.__table__,
    WorkspaceMembership.__table__,
    OperatorRefreshToken.__table__,
    OperatorInvite.__table__,
]


class PasswordHashingTests(unittest.TestCase):
    def test_hash_and_verify_round_trip(self) -> None:
        encoded = hash_password("local-password")
        self.assertTrue(encoded.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("local-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))


class AuthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        get_engine.cache_clear()
        auth_rate_limiter.reset()
        os.environ["AUTH_REGISTRATION_ENABLED"] = "true"
        os.environ["AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "100"
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def _fk_on(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=_AUTH_TABLES)
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.app = create_app()

        def _override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db_session] = _override_db
        with self.Session() as db:
            ensure_default_workspace(db)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        get_settings.cache_clear()
        get_engine.cache_clear()
        auth_rate_limiter.reset()
        Base.metadata.drop_all(self.engine, tables=list(reversed(_AUTH_TABLES)))
        self.engine.dispose()

    def test_login_without_register_returns_401(self) -> None:
        with TestClient(self.app) as client:
            response = client.post(
                "/auth/login",
                json={"email": "operator@local.test", "password": "local-password", "workspace_slug": "local-workspace"},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid email or password")

    def test_register_then_login_and_me(self) -> None:
        with TestClient(self.app) as client:
            register = client.post(
                "/auth/register",
                json={
                    "display_name": "Local Operator",
                    "email": "operator@local.test",
                    "password": "local-password",
                    "workspace_slug": "local-workspace",
                },
            )
            self.assertEqual(register.status_code, 200, register.text)
            token_payload = register.json()
            self.assertEqual(token_payload["token_type"], "bearer")
            self.assertTrue(token_payload["access_token"])
            self.assertTrue(token_payload["refresh_token"])
            self.assertEqual(token_payload["subject"], "operator@local.test")
            self.assertTrue(token_payload["operator_id"])
            self.assertIn("owner", token_payload["roles"])

            bad_login = client.post(
                "/auth/login",
                json={"email": "operator@local.test", "password": "wrong-password", "workspace_slug": "local-workspace"},
            )
            self.assertEqual(bad_login.status_code, 401)

            login = client.post(
                "/auth/login",
                json={"email": "operator@local.test", "password": "local-password", "workspace_slug": "local-workspace"},
            )
            self.assertEqual(login.status_code, 200)
            token = login.json()["access_token"]
            self.assertTrue(login.json()["refresh_token"])

            me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 200)
            me_payload = me.json()
            self.assertEqual(me_payload["email"], "operator@local.test")
            self.assertEqual(me_payload["workspace_slug"], "local")
            self.assertEqual(me_payload["display_name"], "Local Operator")
            self.assertTrue(me_payload["memberships"])
            self.assertEqual(me_payload["memberships"][0]["role"], "owner")

            protected = client.get("/filter-presets", headers={"Authorization": f"Bearer {token}"})
            self.assertNotEqual(protected.status_code, 401)

    def test_refresh_rotates_and_logout_revokes(self) -> None:
        with TestClient(self.app) as client:
            register = client.post(
                "/auth/register",
                json={
                    "email": "refresh@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                },
            )
            self.assertEqual(register.status_code, 200, register.text)
            refresh = register.json()["refresh_token"]

            rotated = client.post("/auth/refresh", json={"refresh_token": refresh})
            self.assertEqual(rotated.status_code, 200, rotated.text)
            new_access = rotated.json()["access_token"]
            new_refresh = rotated.json()["refresh_token"]
            self.assertNotEqual(new_refresh, refresh)

            reuse = client.post("/auth/refresh", json={"refresh_token": refresh})
            self.assertEqual(reuse.status_code, 401)

            me = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
            self.assertEqual(me.status_code, 200)

            logout = client.post("/auth/logout", json={"refresh_token": new_refresh})
            self.assertEqual(logout.status_code, 200)

            after_logout = client.post("/auth/refresh", json={"refresh_token": new_refresh})
            self.assertEqual(after_logout.status_code, 401)

    def test_registration_can_be_disabled(self) -> None:
        os.environ["AUTH_REGISTRATION_ENABLED"] = "false"
        get_settings.cache_clear()
        with TestClient(self.app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "blocked@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_invite_create_and_accept(self) -> None:
        with TestClient(self.app) as client:
            owner = client.post(
                "/auth/register",
                json={
                    "email": "owner@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "display_name": "Owner",
                },
            )
            self.assertEqual(owner.status_code, 200, owner.text)
            owner_token = owner.json()["access_token"]

            invite = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"email": "invitee@local.test", "role": "operator"},
            )
            self.assertEqual(invite.status_code, 200, invite.text)
            invite_token = invite.json()["invite_token"]
            self.assertTrue(invite_token)

            accepted = client.post(
                "/auth/invites/accept",
                json={
                    "invite_token": invite_token,
                    "password": "invitee-password",
                    "display_name": "Invitee",
                },
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertTrue(accepted.json()["access_token"])
            self.assertTrue(accepted.json()["refresh_token"])
            self.assertIn("operator", accepted.json()["roles"])

            me = client.get("/auth/me", headers={"Authorization": f"Bearer {accepted.json()['access_token']}"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["email"], "invitee@local.test")

    def test_duplicate_register_returns_409(self) -> None:
        body = {
            "display_name": "Local Operator",
            "email": "dup@local.test",
            "password": "local-password",
            "workspace_slug": "local",
        }
        with TestClient(self.app) as client:
            first = client.post("/auth/register", json=body)
            second = client.post("/auth/register", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_me_without_token_returns_401(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_backend_auth_ui_is_public_html(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/auth/ui")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        body = response.text
        self.assertIn('id="login-form"', body)
        self.assertIn("/auth/login", body)
        self.assertIn("/docs", body)
        self.assertIn("API Console", body)
        self.assertIn(":3000/auth/login", body)
        self.assertIn(":3000/auth/ops/login", body)
        self.assertIn('client: "api-ui"', body)
        self.assertIn("read-only", body.lower())
        self.assertIn("Get API token", body)

    def test_access_token_includes_issuer_and_audience(self) -> None:
        with TestClient(self.app) as client:
            register = client.post(
                "/auth/register",
                json={"email": "claims@local.test", "password": "local-password", "workspace_slug": "local"},
            )
            self.assertEqual(register.status_code, 200, register.text)
            token = register.json()["access_token"]
        import base64
        import json

        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
        self.assertEqual(payload.get("iss"), "reup-douyin-test")
        self.assertEqual(payload.get("aud"), "reup-douyin-web-test")
        self.assertEqual(payload.get("azp"), "operator")
        self.assertIn("operator", payload.get("scopes") or [])

    def test_api_ui_token_is_read_only_on_product_routes(self) -> None:
        with TestClient(self.app) as client:
            register = client.post(
                "/auth/register",
                json={
                    "email": "apiui@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "operator",
                },
            )
            self.assertEqual(register.status_code, 200, register.text)

            api_login = client.post(
                "/auth/login",
                json={
                    "email": "apiui@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "api-ui",
                },
            )
            self.assertEqual(api_login.status_code, 200, api_login.text)
            self.assertEqual(api_login.json()["client"], "api-ui")
            self.assertEqual(api_login.json()["audience"], "reup-douyin-api-test")
            api_token = api_login.json()["access_token"]

            me = client.get("/auth/me", headers={"Authorization": f"Bearer {api_token}"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["client"], "api-ui")

            read_ok = client.get("/filter-presets", headers={"Authorization": f"Bearer {api_token}"})
            self.assertNotEqual(read_ok.status_code, 401)
            self.assertNotEqual(read_ok.status_code, 403)

            write_blocked = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {api_token}"},
                json={"email": "blocked@local.test", "role": "operator"},
            )
            self.assertEqual(write_blocked.status_code, 403)

            web_login = client.post(
                "/auth/login",
                json={
                    "email": "apiui@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "operator",
                },
            )
            self.assertEqual(web_login.status_code, 200)
            web_token = web_login.json()["access_token"]
            invite = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {web_token}"},
                json={"email": "allowed-invite@local.test", "role": "operator"},
            )
            self.assertEqual(invite.status_code, 200, invite.text)

    def test_ops_login_requires_owner_and_blocks_operator_surface_on_ops_api(self) -> None:
        with TestClient(self.app) as client:
            owner = client.post(
                "/auth/register",
                json={
                    "email": "ops-owner@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "operator",
                },
            )
            self.assertEqual(owner.status_code, 200, owner.text)
            owner_token = owner.json()["access_token"]

            invite = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"email": "plain-op@local.test", "role": "operator"},
            )
            self.assertEqual(invite.status_code, 200, invite.text)
            accepted = client.post(
                "/auth/invites/accept",
                json={
                    "invite_token": invite.json()["invite_token"],
                    "password": "local-password",
                    "display_name": "Plain Op",
                },
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)

            plain_ops = client.post(
                "/auth/login",
                json={
                    "email": "plain-op@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "ops",
                },
            )
            self.assertEqual(plain_ops.status_code, 403)

            ops_login = client.post(
                "/auth/login",
                json={
                    "email": "ops-owner@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "ops",
                },
            )
            self.assertEqual(ops_login.status_code, 200, ops_login.text)
            self.assertEqual(ops_login.json()["client"], "ops")
            self.assertEqual(ops_login.json()["audience"], "reup-douyin-ops-test")
            ops_token = ops_login.json()["access_token"]

        # Separate client so 5xx from missing sqlite jobs tables does not abort the case.
        with TestClient(self.app, raise_server_exceptions=False) as client:
            ops_metrics = client.get("/ops/metrics", headers={"Authorization": f"Bearer {ops_token}"})
            self.assertNotEqual(ops_metrics.status_code, 401)
            self.assertNotEqual(ops_metrics.status_code, 403)

            studio_blocked = client.get("/ops/metrics", headers={"Authorization": f"Bearer {owner_token}"})
            self.assertEqual(studio_blocked.status_code, 403)

            studio_pipeline = client.get(
                "/pipeline-dashboard",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            self.assertNotEqual(
                studio_pipeline.status_code,
                403,
                "Operator Studio token must reach the pipeline dashboard aggregation API",
            )
            self.assertNotEqual(studio_pipeline.status_code, 401)

            ops_legacy = client.get(
                "/ops/pipeline-dashboard",
                headers={"Authorization": f"Bearer {ops_token}"},
            )
            self.assertEqual(
                ops_legacy.status_code,
                404,
                "Legacy Ops-prefixed pipeline dashboard path must be retired",
            )

    def test_register_rejects_api_ui_client(self) -> None:
        with TestClient(self.app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "api-register@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "api-ui",
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_register_rejects_ops_client(self) -> None:
        with TestClient(self.app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "ops-register@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "client": "ops",
                },
            )
        self.assertEqual(response.status_code, 403)

    def test_workspace_users_admin_list_invite_revoke_role_disable(self) -> None:
        with TestClient(self.app) as client:
            owner = client.post(
                "/auth/register",
                json={
                    "email": "users-owner@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                    "display_name": "Users Owner",
                },
            )
            self.assertEqual(owner.status_code, 200, owner.text)
            owner_token = owner.json()["access_token"]
            owner_id = owner.json()["operator_id"]

            members = client.get("/auth/workspace/members", headers={"Authorization": f"Bearer {owner_token}"})
            self.assertEqual(members.status_code, 200, members.text)
            member_rows = members.json()["members"]
            self.assertEqual(len(member_rows), 1)
            self.assertEqual(member_rows[0]["email"], "users-owner@local.test")
            self.assertEqual(member_rows[0]["role"], "owner")
            self.assertTrue(member_rows[0]["is_active"])

            invite = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"email": "users-op@local.test", "role": "operator"},
            )
            self.assertEqual(invite.status_code, 200, invite.text)
            invite_id = invite.json()["invite_id"]

            pending = client.get("/auth/workspace/invites", headers={"Authorization": f"Bearer {owner_token}"})
            self.assertEqual(pending.status_code, 200, pending.text)
            self.assertEqual(len(pending.json()["invites"]), 1)
            self.assertEqual(pending.json()["invites"][0]["email"], "users-op@local.test")
            self.assertEqual(pending.json()["invites"][0]["status"], "pending")

            revoke = client.post(
                f"/auth/workspace/invites/{invite_id}/revoke",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            self.assertEqual(revoke.status_code, 200, revoke.text)
            pending_after = client.get("/auth/workspace/invites", headers={"Authorization": f"Bearer {owner_token}"})
            self.assertEqual(pending_after.json()["invites"], [])

            invite2 = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"email": "users-op@local.test", "role": "operator"},
            )
            self.assertEqual(invite2.status_code, 200, invite2.text)
            accepted = client.post(
                "/auth/invites/accept",
                json={
                    "invite_token": invite2.json()["invite_token"],
                    "password": "local-password",
                    "display_name": "Users Op",
                },
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            op_id = accepted.json()["operator_id"]
            op_token = accepted.json()["access_token"]

            members2 = client.get("/auth/workspace/members", headers={"Authorization": f"Bearer {owner_token}"})
            self.assertEqual(len(members2.json()["members"]), 2)

            forbidden = client.get("/auth/workspace/members", headers={"Authorization": f"Bearer {op_token}"})
            self.assertEqual(forbidden.status_code, 403)

            promoted = client.patch(
                f"/auth/workspace/members/{op_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"role": "admin"},
            )
            self.assertEqual(promoted.status_code, 200, promoted.text)
            self.assertEqual(promoted.json()["role"], "admin")

            disabled = client.patch(
                f"/auth/workspace/members/{op_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"is_active": False},
            )
            self.assertEqual(disabled.status_code, 200, disabled.text)
            self.assertFalse(disabled.json()["is_active"])

            login_disabled = client.post(
                "/auth/login",
                json={
                    "email": "users-op@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                },
            )
            self.assertIn(login_disabled.status_code, {401, 403})

            enabled = client.patch(
                f"/auth/workspace/members/{op_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"is_active": True},
            )
            self.assertEqual(enabled.status_code, 200, enabled.text)
            self.assertTrue(enabled.json()["is_active"])

            renamed = client.patch(
                f"/auth/workspace/members/{op_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"display_name": "Users Operator Renamed"},
            )
            self.assertEqual(renamed.status_code, 200, renamed.text)
            self.assertEqual(renamed.json()["display_name"], "Users Operator Renamed")
            self.assertEqual(renamed.json()["role"], "admin")
            self.assertTrue(renamed.json()["is_active"])

            profiled = client.patch(
                f"/auth/workspace/members/{op_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={
                    "phone": "+84 90 123 4567",
                    "address": "District 1, HCMC",
                    "notes": "Primary reup operator",
                },
            )
            self.assertEqual(profiled.status_code, 200, profiled.text)
            self.assertEqual(profiled.json()["phone"], "+84 90 123 4567")
            self.assertEqual(profiled.json()["address"], "District 1, HCMC")
            self.assertEqual(profiled.json()["notes"], "Primary reup operator")

            reset = client.post(
                f"/auth/workspace/members/{op_id}/reset-password",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            self.assertEqual(reset.status_code, 200, reset.text)
            temp_password = reset.json()["temporary_password"]
            self.assertTrue(temp_password)
            old_login = client.post(
                "/auth/login",
                json={
                    "email": "users-op@local.test",
                    "password": "local-password",
                    "workspace_slug": "local",
                },
            )
            self.assertIn(old_login.status_code, {401, 403})
            new_login = client.post(
                "/auth/login",
                json={
                    "email": "users-op@local.test",
                    "password": temp_password,
                    "workspace_slug": "local",
                },
            )
            self.assertEqual(new_login.status_code, 200, new_login.text)

            # Last owner cannot demote or disable self.
            demote_self = client.patch(
                f"/auth/workspace/members/{owner_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"role": "admin"},
            )
            self.assertEqual(demote_self.status_code, 400)
            disable_self = client.patch(
                f"/auth/workspace/members/{owner_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"is_active": False},
            )
            self.assertEqual(disable_self.status_code, 400)

            invite3 = client.post(
                "/auth/invites",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"email": "users-rotate@local.test", "role": "viewer"},
            )
            self.assertEqual(invite3.status_code, 200, invite3.text)
            old_token = invite3.json()["invite_token"]
            rotate_id = invite3.json()["invite_id"]
            rotated = client.post(
                f"/auth/workspace/invites/{rotate_id}/rotate",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            self.assertEqual(rotated.status_code, 200, rotated.text)
            new_token = rotated.json()["invite_token"]
            self.assertTrue(new_token)
            self.assertNotEqual(new_token, old_token)
            self.assertEqual(rotated.json()["email"], "users-rotate@local.test")

            old_accept = client.post(
                "/auth/invites/accept",
                json={
                    "invite_token": old_token,
                    "password": "local-password",
                    "display_name": "Stale",
                },
            )
            self.assertEqual(old_accept.status_code, 400)
            new_accept = client.post(
                "/auth/invites/accept",
                json={
                    "invite_token": new_token,
                    "password": "local-password",
                    "display_name": "Rotated User",
                },
            )
            self.assertEqual(new_accept.status_code, 200, new_accept.text)


class AuthRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        get_engine.cache_clear()
        auth_rate_limiter.reset()
        os.environ["AUTH_REGISTRATION_ENABLED"] = "true"
        os.environ["AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "3"
        os.environ["AUTH_RATE_LIMIT_WINDOW_SECONDS"] = "300"
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def _fk_on(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=_AUTH_TABLES)
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.app = create_app()

        def _override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db_session] = _override_db
        with self.Session() as db:
            ensure_default_workspace(db)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        get_settings.cache_clear()
        get_engine.cache_clear()
        auth_rate_limiter.reset()
        os.environ["AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "100"
        Base.metadata.drop_all(self.engine, tables=list(reversed(_AUTH_TABLES)))
        self.engine.dispose()

    def test_login_rate_limit_returns_429(self) -> None:
        body = {"email": "ratelimit@local.test", "password": "wrong-password", "workspace_slug": "local"}
        with TestClient(self.app) as client:
            codes = [client.post("/auth/login", json=body).status_code for _ in range(4)]
        self.assertEqual(codes[:3], [401, 401, 401])
        self.assertEqual(codes[3], 429)


if __name__ == "__main__":
    unittest.main()
