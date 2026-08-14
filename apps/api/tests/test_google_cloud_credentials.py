from __future__ import annotations

import json
from base64 import b64encode
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.services.workspace_settings_service import TTS_AI_KEY, TtsAiConfig, WorkspaceSettingsService
from src.tts_pipeline.google_cloud_credentials import (
    GOOGLE_CLOUD_TTS_BASE_URL,
    GOOGLE_CREDENTIAL_MODE_ADC,
    GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT,
    GoogleCloudCredentialError,
    clear_google_token_cache,
    default_google_http_connector_options,
    resolve_google_access_token,
    validate_google_service_account_json,
)
from src.tts_pipeline.provider_factory import build_default_tts_provider


def _service_account_json() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "tts-project",
            "private_key_id": "unit-test",
            "private_key": pem,
            "client_email": "tts-runtime@tts-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


def test_service_account_validation_returns_only_safe_metadata() -> None:
    raw = _service_account_json()
    metadata = validate_google_service_account_json(raw)

    assert metadata.client_email == "tts-runtime@tts-project.iam.gserviceaccount.com"
    assert metadata.project_id == "tts-project"
    assert "PRIVATE KEY" in metadata.normalized_json

    invalid = json.loads(raw)
    invalid["token_uri"] = "https://attacker.example/token"
    with pytest.raises(GoogleCloudCredentialError, match="google_service_account_token_uri_invalid"):
        validate_google_service_account_json(json.dumps(invalid))


def test_internal_config_repr_redacts_both_google_secrets() -> None:
    rendered = repr(
        TtsAiConfig(
            api_key="oauth-secret",
            google_service_account_json="private-json-secret",
        )
    )

    assert "oauth-secret" not in rendered
    assert "private-json-secret" not in rendered


def test_google_connector_is_fixed_to_oauth_voices_and_base64_audio() -> None:
    options = default_google_http_connector_options({})
    connector = options["http_connector"]

    assert options["expressive_tts"]["mode"] == "required"
    assert connector["auth"] == {
        "type": "bearer",
        "header_name": "Authorization",
        "prefix": "Bearer ",
        "test_method": "GET",
        "test_path": "/voices",
    }
    assert connector["catalog"]["voices"]["items_path"] == "voices"
    assert connector["synthesis"]["path"] == "/text:synthesize"
    assert connector["synthesis"]["body"]["input"] == {"ssml": "{{ssml_text}}"}
    assert connector["synthesis"]["body"]["audioConfig"]["speakingRate"] == 1.0
    assert connector["synthesis"]["response"]["audio_path"] == "audioContent"

    localized = default_google_http_connector_options({}, language_code="vi-VN")["http_connector"]
    assert localized["auth"]["test_path"] == "/voices?languageCode=vi-VN"
    assert localized["catalog"]["voices"]["path"] == "/voices?languageCode=vi-VN"


def test_service_account_token_is_cached_without_serializing_it() -> None:
    raw = _service_account_json()
    fake_credentials = SimpleNamespace(
        token="oauth-token-not-persisted",
        expiry=datetime.fromtimestamp(5000, tz=timezone.utc),
        refresh=MagicMock(),
    )
    clear_google_token_cache()
    with patch(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        return_value=fake_credentials,
    ) as factory:
        first = resolve_google_access_token(
            credential_mode=GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT,
            service_account_json=raw,
            now=lambda: 1000,
        )
        second = resolve_google_access_token(
            credential_mode=GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT,
            service_account_json=raw,
            now=lambda: 1001,
        )

    assert first == second == "oauth-token-not-persisted"
    assert factory.call_count == 1
    assert fake_credentials.refresh.call_count == 1


def test_adc_refresh_uses_host_credentials() -> None:
    fake_credentials = SimpleNamespace(
        token="adc-token",
        expiry=datetime.fromtimestamp(6000, tz=timezone.utc),
        refresh=MagicMock(),
    )
    clear_google_token_cache()
    with patch("google.auth.default", return_value=(fake_credentials, "tts-project")) as default:
        token = resolve_google_access_token(
            credential_mode=GOOGLE_CREDENTIAL_MODE_ADC,
            service_account_json=None,
            now=lambda: 1000,
        )

    assert token == "adc-token"
    default.assert_called_once()
    fake_credentials.refresh.assert_called_once()


def test_workspace_persists_only_encrypted_service_account_and_public_metadata() -> None:
    raw = _service_account_json()
    workspace = SimpleNamespace(id=uuid4(), settings_json={})
    db = MagicMock()
    db.get.return_value = workspace
    service = WorkspaceSettingsService(db)
    payload = {
        "enabled": True,
        "provider": "google",
        "voice_id": "vi-VN-Neural2-A",
        "speaking_rate": 1.0,
        "language_code": "vi-VN",
        "model_id": "",
        "credential_mode": GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT,
        "google_service_account_json": raw,
        "base_url": "https://credential-exfiltration.example/v1",
        "timeout_seconds": 120,
        "fallback_provider": "none",
        "fallback_voice_id": "",
        "local_backend": "auto",
        "device": "auto",
        "cli_binary": "",
        "options_json": {},
    }

    credential_settings = SimpleNamespace(
        platform_credential_encryption_key_ref="base64:" + b64encode(b"x" * 32).decode("ascii"),
        platform_credential_local_key_path="unused-in-this-test",
        app_env="test",
    )
    with patch("src.core.settings.get_settings", return_value=credential_settings):
        saved = service.set_tts_ai(workspace.id, payload)
        public = service.get_tts_ai_public(workspace.id)

    persisted = workspace.settings_json[TTS_AI_KEY]["profiles"][0]
    assert saved.google_service_account_json == validate_google_service_account_json(raw).normalized_json
    assert persisted["google_service_account_encrypted"].startswith("envelope-v1:")
    assert persisted["base_url"] == GOOGLE_CLOUD_TTS_BASE_URL
    assert "private_key" not in str(persisted)
    assert public["google_service_account_set"] is True
    assert public["google_service_account_email"] == "tts-runtime@tts-project.iam.gserviceaccount.com"
    assert public["google_service_account_project_id"] == "tts-project"
    assert "google_service_account_json" not in public
    assert "PRIVATE KEY" not in str(public)


def test_google_runtime_never_sends_oauth_token_to_operator_base_url() -> None:
    cfg = SimpleNamespace(
        enabled=True,
        provider="google",
        credential_mode="google_oauth_token",
        google_service_account_json=None,
        voice_id="vi-VN-Neural2-A",
        speaking_rate=1.0,
        language_code="vi-VN",
        model_id="",
        api_key="temporary-oauth-token",
        base_url="https://credential-exfiltration.example/v1",
        timeout_seconds=120,
        fallback_provider="none",
        fallback_voice_id="",
        local_backend="auto",
        device="auto",
        cli_binary="",
        options_json={},
    )

    provider = build_default_tts_provider(workspace_tts=cfg)

    assert provider.provider_name == "google"
    assert provider.base_url == GOOGLE_CLOUD_TTS_BASE_URL
