from __future__ import annotations

import os
import unittest
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_AUTH_REQUIRED", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-thirty-two-characters")

from fastapi.testclient import TestClient

from src.core.auth import create_internal_hs256_token
from src.core.settings import get_settings
from src.main import create_app


class AuthenticationFirewallTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        self.app = create_app()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        get_settings.cache_clear()

    def test_protected_route_without_bearer_token_returns_401(self) -> None:
        with TestClient(self.app) as client:
            response = client.get("/filter-presets")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Missing bearer token")

    def test_application_routes_are_protected_even_though_openapi_schema_remains_public(self) -> None:
        with TestClient(self.app) as client:
            openapi_response = client.get("/openapi.json")
            protected_response = client.get("/douyin-extension/status")

        self.assertEqual(openapi_response.status_code, 200)
        self.assertEqual(protected_response.status_code, 401)

    def test_protected_route_with_valid_bearer_token_reaches_handler(self) -> None:
        settings = get_settings()
        token = create_internal_hs256_token(
            subject="operator-1",
            workspace_id=uuid4(),
            secret=settings.jwt_secret_key,
            roles=["operator"],
            issuer=settings.jwt_issuer,
            audience=settings.effective_web_audience,
            azp="operator",
            scopes=["operator"],
        )

        with TestClient(self.app) as client:
            response = client.get("/filter-presets", headers={"Authorization": f"Bearer {token}"})

        self.assertNotEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
