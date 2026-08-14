"""Google Cloud TTS credential and OAuth boundary.

Service-account JSON is validated before encrypted persistence. Runtime code
uses google-auth to exchange it (or host ADC) for a short-lived OAuth token.
The token cache is process-local, bounded by credential fingerprint, and never
serialized, logged, or returned through an API response.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import urllib.parse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key


GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT = "google_service_account"
GOOGLE_CREDENTIAL_MODE_ADC = "google_adc"
GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN = "google_oauth_token"
GOOGLE_CREDENTIAL_MODES = frozenset(
    {
        GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT,
        GOOGLE_CREDENTIAL_MODE_ADC,
        GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN,
    }
)
GOOGLE_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
GOOGLE_CLOUD_TTS_BASE_URL = "https://texttospeech.googleapis.com/v1"
GOOGLE_SERVICE_ACCOUNT_MAX_BYTES = 64 * 1024
GOOGLE_TOKEN_REFRESH_SKEW_SECONDS = 300
GOOGLE_TOKEN_FALLBACK_TTL_SECONDS = 3000
GOOGLE_TOKEN_CACHE_MAX_ENTRIES = 32
_CLIENT_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.gserviceaccount\.com$")
_ALLOWED_TOKEN_URIS = frozenset(
    {
        "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/oauth2/v4/token",
    }
)


class GoogleCloudCredentialError(ValueError):
    """Operator-safe Google credential failure."""


@dataclass(frozen=True)
class GoogleServiceAccountMetadata:
    normalized_json: str
    client_email: str
    project_id: str


@dataclass(frozen=True)
class _CachedGoogleToken:
    token: str
    expires_at: float


_TOKEN_CACHE: dict[str, _CachedGoogleToken] = {}
_TOKEN_CACHE_LOCK = threading.RLock()


def normalize_google_credential_mode(value: Any, *, provider: str = "") -> str:
    mode = str(value or "").strip().lower()
    if mode in GOOGLE_CREDENTIAL_MODES:
        return mode
    if str(provider or "").strip().lower() == "google":
        return GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT
    return "api_key"


def validate_google_service_account_json(raw: str) -> GoogleServiceAccountMetadata:
    text = str(raw or "").strip()
    if not text:
        raise GoogleCloudCredentialError("google_service_account_required")
    if len(text.encode("utf-8")) > GOOGLE_SERVICE_ACCOUNT_MAX_BYTES:
        raise GoogleCloudCredentialError("google_service_account_too_large")
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise GoogleCloudCredentialError("google_service_account_invalid_json") from exc
    if not isinstance(payload, dict) or str(payload.get("type") or "") != "service_account":
        raise GoogleCloudCredentialError("google_service_account_type_invalid")

    client_email = str(payload.get("client_email") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    private_key = str(payload.get("private_key") or "")
    token_uri = str(payload.get("token_uri") or "").strip()
    if not _CLIENT_EMAIL_RE.fullmatch(client_email):
        raise GoogleCloudCredentialError("google_service_account_email_invalid")
    if not project_id or len(project_id) > 200 or any(char in project_id for char in "\r\n\0"):
        raise GoogleCloudCredentialError("google_service_account_project_invalid")
    if token_uri not in _ALLOWED_TOKEN_URIS:
        raise GoogleCloudCredentialError("google_service_account_token_uri_invalid")
    try:
        key = load_pem_private_key(private_key.encode("utf-8"), password=None)
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        raise GoogleCloudCredentialError("google_service_account_private_key_invalid") from exc
    if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
        raise GoogleCloudCredentialError("google_service_account_private_key_invalid")

    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return GoogleServiceAccountMetadata(
        normalized_json=normalized,
        client_email=client_email,
        project_id=project_id,
    )


def default_google_http_connector_options(
    options: Mapping[str, Any] | None = None,
    *,
    language_code: str = "",
) -> dict[str, Any]:
    """Return Google Cloud TTS mapping with OAuth bearer authority."""

    output = deepcopy(dict(options or {}))
    expressive = output.get("expressive_tts")
    if not isinstance(expressive, dict):
        expressive = {}
    expressive.setdefault("mode", "required")
    output["expressive_tts"] = expressive
    normalized_language = str(language_code or "").strip()
    voices_path = "/voices"
    if re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", normalized_language):
        voices_path += "?languageCode=" + urllib.parse.quote(normalized_language, safe="-")
    connector = output.get("http_connector")
    if not isinstance(connector, dict):
        connector = {}
    connector.update({"version": 1, "mode": "custom"})
    connector["auth"] = {
        "type": "bearer",
        "header_name": "Authorization",
        "prefix": "Bearer ",
        "test_method": "GET",
        "test_path": voices_path,
    }
    catalog = connector.get("catalog")
    if not isinstance(catalog, dict):
        catalog = {}
    catalog["voices"] = {
        "path": voices_path,
        "items_path": "voices",
        "id_path": "name",
        "label_path": "name",
        "languages_path": "languageCodes",
        "gender_path": "ssmlGender",
    }
    catalog.pop("models", None)
    catalog.pop("languages", None)
    connector["catalog"] = catalog
    connector["synthesis"] = {
        "path": "/text:synthesize",
        "method": "POST",
        "content_type": "application/json",
        "body": {
            # SSML is the execution path for emotion/prosody.  The adapter
            # still falls back to plain text when a request has no SSML.
            "input": {"ssml": "{{ssml_text}}"},
            "voice": {
                "languageCode": "{{language_code}}",
                "name": "{{voice_id}}",
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                # The adapter embeds the effective duration rate together with
                # the local prosody pace in <prosody rate=...>. Keeping this
                # field neutral avoids applying speaking rate twice.
                "speakingRate": 1.0,
            },
        },
        "response": {
            "type": "json_base64",
            "audio_path": "audioContent",
            "mime_type": "audio/mpeg",
            "file_extension": "mp3",
        },
    }
    output["http_connector"] = connector
    return output


def resolve_google_access_token(
    *,
    credential_mode: str,
    service_account_json: str | None,
    timeout_seconds: float = 30.0,
    now: Callable[[], float] = time.time,
) -> str:
    mode = normalize_google_credential_mode(credential_mode, provider="google")
    if mode == GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN:
        raise GoogleCloudCredentialError("google_oauth_token_required")

    normalized_json = ""
    if mode == GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT:
        normalized_json = validate_google_service_account_json(service_account_json or "").normalized_json
    cache_key = hashlib.sha256(f"{mode}\0{normalized_json}".encode("utf-8")).hexdigest()
    current = now()
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached.expires_at - GOOGLE_TOKEN_REFRESH_SKEW_SECONDS > current:
            return cached.token

    try:
        import google.auth
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import service_account
    except ImportError as exc:
        raise GoogleCloudCredentialError("google_auth_dependency_missing") from exc

    try:
        if mode == GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT:
            info = json.loads(normalized_json)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=[GOOGLE_CLOUD_PLATFORM_SCOPE],
            )
        elif mode == GOOGLE_CREDENTIAL_MODE_ADC:
            credentials, _project_id = google.auth.default(scopes=[GOOGLE_CLOUD_PLATFORM_SCOPE])
        else:
            raise GoogleCloudCredentialError("google_credential_mode_invalid")
        google_request = GoogleAuthRequest()
        try:
            requested_timeout = float(timeout_seconds)
            bounded_timeout = (
                min(max(requested_timeout, 1.0), 60.0)
                if math.isfinite(requested_timeout)
                else 30.0
            )
        except (TypeError, ValueError):
            bounded_timeout = 30.0

        def bounded_request(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", bounded_timeout)
            return google_request(*args, **kwargs)

        credentials.refresh(bounded_request)
    except GoogleCloudCredentialError:
        raise
    except Exception as exc:  # noqa: BLE001 - never expose google-auth credential internals
        raise GoogleCloudCredentialError("google_oauth_refresh_failed") from exc

    token = str(getattr(credentials, "token", "") or "").strip()
    if not token or len(token) > 8192 or any(char in token for char in "\r\n\0"):
        raise GoogleCloudCredentialError("google_oauth_token_invalid")
    expires_at = _credential_expiry_timestamp(getattr(credentials, "expiry", None), current)
    with _TOKEN_CACHE_LOCK:
        for stale_key in [key for key, item in _TOKEN_CACHE.items() if item.expires_at <= current]:
            _TOKEN_CACHE.pop(stale_key, None)
        while len(_TOKEN_CACHE) >= GOOGLE_TOKEN_CACHE_MAX_ENTRIES:
            oldest_key = min(_TOKEN_CACHE, key=lambda key: _TOKEN_CACHE[key].expires_at)
            _TOKEN_CACHE.pop(oldest_key, None)
        _TOKEN_CACHE[cache_key] = _CachedGoogleToken(token=token, expires_at=expires_at)
    return token


def _credential_expiry_timestamp(expiry: Any, current: float) -> float:
    if isinstance(expiry, datetime):
        normalized_expiry = expiry if expiry.tzinfo is not None else expiry.replace(tzinfo=timezone.utc)
        value = normalized_expiry.timestamp()
        if math.isfinite(value) and value > current:
            return value
    return current + GOOGLE_TOKEN_FALLBACK_TTL_SECONDS


def clear_google_token_cache() -> None:
    """Test/revocation hook; production normally relies on expiry."""

    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE.clear()
