"""Declarative, bounded HTTP connector for remote TTS providers.

The connector intentionally implements a small data-mapping language instead
of executing vendor code.  A workspace stores the public manifest at
``options_json.http_connector`` while the API key remains in the existing
secret field.  Every configured endpoint is constrained to the provider base
origin; only an audio URL returned by the provider may use another public
HTTPS origin, and credentials are never forwarded to that URL.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import math
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from io import BytesIO
from typing import Any

from src.tts_pipeline.catalog import (
    TtsCatalogDiscovery,
    TtsLanguageOption,
    TtsModelOption,
    TtsProviderCatalog,
    TtsVoiceOption,
    capabilities_for_provider,
)
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput


HTTP_CONNECTOR_VERSION = 1
HTTP_CONNECTOR_OPTION_KEY = "http_connector"
CONNECTOR_DISCOVERY_TIMEOUT_SECONDS = 10.0
CONNECTOR_SYNTHESIS_TIMEOUT_CAP_SECONDS = 180.0
CONNECTOR_JSON_MAX_BYTES = 2 * 1024 * 1024
CONNECTOR_AUDIO_MAX_BYTES = 32 * 1024 * 1024
CONNECTOR_PROVIDER_ERROR_MAX_BYTES = 8 * 1024
CONNECTOR_PROVIDER_ERROR_MAX_CHARS = 500
CONNECTOR_MAX_OPTIONS = 500
CONNECTOR_POLL_MAX_ATTEMPTS = 60
CONNECTOR_POLL_MAX_INTERVAL_SECONDS = 5.0
CONNECTOR_MAX_MANIFEST_DEPTH = 12
CONNECTOR_MAX_MANIFEST_NODES = 2_000

_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,80}$")
_JSON_PATH_RE = re.compile(r"^[A-Za-z0-9_$.[\]*-]{0,256}$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)
_ALLOWED_PLACEHOLDERS = frozenset(
    {
        "text",
        "rendered_text",
        "voice_direction",
        "sample_context",
        "audio_tags",
        "ssml_text",
        "prosody_state",
        "performance_chunk_id",
        "model_id",
        "voice_id",
        "language_code",
        "speaking_rate",
        "target_duration_seconds",
        "job_id",
    }
)
_SECRET_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(api[_-]?key|access[_-]?token|token|secret|credential|password|authorization|cookie)(?:$|[_-])|(?:apiKey|accessToken|clientSecret|authToken|refreshToken)$",
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:^bearer\s+\S+|^sk[-_][A-Za-z0-9_-]{8,}|^eyJ[A-Za-z0-9_-]{10,}\.)"
)
_EMBEDDED_SECRET_RE = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/-]{8,}|sk[-_][A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.)"
)
_QUERY_SECRET_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(api[_-]?key|access[_-]?token|token|secret|signature|credential|password|authorization|auth|sig|key)(?:$|[_-])|(?:apiKey|accessToken|clientSecret|authToken|refreshToken)$"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:api[-_]?key|apiKey|access[-_]?token|accessToken|authToken|refreshToken|token|secret|credential|password|authorization|cookie)[\"']?\s*[:=]"
)


class HttpConnectorConfigError(ValueError):
    """Manifest validation failure safe to return to an operator."""


class HttpConnectorRequestError(RuntimeError):
    """Sanitized remote-boundary failure."""

    def __init__(
        self,
        code: str,
        *,
        http_status: int | None = None,
        provider_detail: str = "",
    ):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.provider_detail = provider_detail


@dataclass(frozen=True)
class HttpConnectorAuth:
    type: str = "bearer"  # none | bearer | header | query
    header_name: str = "Authorization"
    prefix: str = "Bearer "
    query_name: str = "api_key"
    test_path: str = ""
    test_method: str = "GET"


@dataclass(frozen=True)
class HttpConnectorOpenApi:
    url: str = ""


@dataclass(frozen=True)
class HttpConnectorCatalogResource:
    path: str
    method: str = "GET"
    content_type: str = "application/json"
    body: Any = field(default_factory=dict)
    items_path: str = ""
    id_path: str = "id"
    label_path: str = "name"
    languages_path: str = ""
    models_path: str = ""
    voices_path: str = ""
    gender_path: str = ""
    description_path: str = ""
    capabilities_path: str = ""


@dataclass(frozen=True)
class HttpConnectorCatalog:
    models: HttpConnectorCatalogResource | None = None
    voices: HttpConnectorCatalogResource | None = None
    languages: HttpConnectorCatalogResource | None = None


@dataclass(frozen=True)
class HttpConnectorResponse:
    type: str = "binary"  # binary | json_base64 | json_url | async_json
    audio_path: str = ""
    mime_type: str = ""
    mime_type_path: str = ""
    duration_path: str = ""
    file_extension: str = ""


@dataclass(frozen=True)
class HttpConnectorPolling:
    job_id_path: str
    poll_path: str
    method: str = "GET"
    content_type: str = "application/json"
    body: Any = field(default_factory=dict)
    status_path: str = "status"
    success_values: tuple[str, ...] = ("completed", "succeeded", "success", "done")
    failure_values: tuple[str, ...] = ("failed", "error", "cancelled", "canceled")
    interval_seconds: float = 1.0
    max_attempts: int = 30
    response_type: str = "json_url"
    audio_path: str = ""
    mime_type_path: str = ""
    duration_path: str = ""


@dataclass(frozen=True)
class HttpConnectorSynthesis:
    path: str
    method: str = "POST"
    content_type: str = "application/json"
    body: Any = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    response: HttpConnectorResponse = field(default_factory=HttpConnectorResponse)
    polling: HttpConnectorPolling | None = None


@dataclass(frozen=True)
class HttpConnectorManifest:
    version: int = HTTP_CONNECTOR_VERSION
    mode: str = "auto"  # auto | openapi | custom
    auth: HttpConnectorAuth = field(default_factory=HttpConnectorAuth)
    openapi: HttpConnectorOpenApi = field(default_factory=HttpConnectorOpenApi)
    catalog: HttpConnectorCatalog = field(default_factory=HttpConnectorCatalog)
    synthesis: HttpConnectorSynthesis | None = None


@dataclass(frozen=True)
class _HttpResponse:
    status: int
    body: bytes
    content_type: str


Resolver = Callable[..., Sequence[tuple[Any, ...]]]
OpenFunction = Callable[..., Any]


def _clean_endpoint(
    value: Any,
    *,
    field_name: str,
    required: bool = False,
    allowed_placeholders: frozenset[str] = frozenset(),
) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise HttpConnectorConfigError(f"{field_name} is required")
    if len(text) > 1000 or any(char in text for char in "\r\n\0"):
        raise HttpConnectorConfigError(f"{field_name} is invalid")
    unknown = {
        match.group(1).lower()
        for match in _PLACEHOLDER_RE.finditer(text)
        if match.group(1).lower() not in allowed_placeholders
    }
    if unknown:
        raise HttpConnectorConfigError(
            f"{field_name} contains unsupported placeholders: {', '.join(sorted(unknown))}"
        )
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        raise HttpConnectorConfigError(f"{field_name} must use HTTP(S)")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise HttpConnectorConfigError(f"{field_name} is invalid")
    decoded_path = urllib.parse.unquote(parsed.path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise HttpConnectorConfigError(f"{field_name} contains traversal")
    for query_key, query_value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        if _QUERY_SECRET_KEY_RE.search(query_key) or _EMBEDDED_SECRET_RE.search(query_value):
            raise HttpConnectorConfigError(
                f"{field_name} cannot contain credentials in its query string"
            )
    return text


def _clean_json_path(value: Any, *, field_name: str, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    if not _JSON_PATH_RE.fullmatch(text):
        raise HttpConnectorConfigError(f"{field_name} uses an unsupported JSON path")
    for part in _json_path_parts(text):
        if _SECRET_KEY_RE.search(part):
            raise HttpConnectorConfigError(
                f"{field_name} cannot point at credential fields"
            )
    return text


def _clean_header_name(value: Any, *, field_name: str, default: str) -> str:
    text = str(value or default).strip()
    if not _HEADER_NAME_RE.fullmatch(text):
        raise HttpConnectorConfigError(f"{field_name} is invalid")
    return text


def _validate_template(value: Any, *, field_name: str, depth: int = 0, nodes: list[int] | None = None) -> Any:
    node_counter = nodes if nodes is not None else [0]
    node_counter[0] += 1
    if depth > CONNECTOR_MAX_MANIFEST_DEPTH or node_counter[0] > CONNECTOR_MAX_MANIFEST_NODES:
        raise HttpConnectorConfigError(f"{field_name} is too deeply nested")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        unknown = {
            match.group(1).lower()
            for match in _PLACEHOLDER_RE.finditer(value)
            if match.group(1).lower() not in _ALLOWED_PLACEHOLDERS
        }
        if unknown:
            raise HttpConnectorConfigError(
                f"{field_name} contains unsupported placeholders: {', '.join(sorted(unknown))}"
            )
        if len(value) > 20_000:
            raise HttpConnectorConfigError(f"{field_name} is too large")
        if _SECRET_VALUE_RE.search(value.strip()):
            raise HttpConnectorConfigError(
                f"{field_name} appears to contain a secret; store credentials in the API key field"
            )
        return value
    if isinstance(value, list):
        if len(value) > 200:
            raise HttpConnectorConfigError(f"{field_name} is too large")
        return [
            _validate_template(item, field_name=field_name, depth=depth + 1, nodes=node_counter)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > 200:
            raise HttpConnectorConfigError(f"{field_name} is too large")
        output: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            if not key or len(key) > 200 or any(char in key for char in "\r\n\0"):
                raise HttpConnectorConfigError(f"{field_name} contains an invalid key")
            if _SECRET_KEY_RE.search(key) and raw_value not in (None, ""):
                raise HttpConnectorConfigError(
                    f"{field_name}.{key} cannot store credentials; use http_connector.auth"
                )
            output[key] = _validate_template(
                raw_value,
                field_name=field_name,
                depth=depth + 1,
                nodes=node_counter,
            )
        return output
    raise HttpConnectorConfigError(f"{field_name} contains an unsupported value")


def _reject_manifest_secrets(
    value: Any,
    *,
    path: str = "http_connector",
    depth: int = 0,
    nodes: list[int] | None = None,
) -> None:
    """Reject credentials hidden in aliases or unknown manifest fields."""

    node_counter = nodes if nodes is not None else [0]
    node_counter[0] += 1
    if depth > CONNECTOR_MAX_MANIFEST_DEPTH or node_counter[0] > CONNECTOR_MAX_MANIFEST_NODES:
        raise HttpConnectorConfigError("http_connector is too deeply nested")

    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = f"{path}.{key}"
            if _SECRET_KEY_RE.search(key) and item not in (None, ""):
                raise HttpConnectorConfigError(
                    f"{item_path} cannot store credentials; use the API key field"
                )
            _reject_manifest_secrets(
                item,
                path=item_path,
                depth=depth + 1,
                nodes=node_counter,
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_manifest_secrets(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
                nodes=node_counter,
            )
        return
    if (
        isinstance(value, str)
        and (_EMBEDDED_SECRET_RE.search(value) or _SECRET_ASSIGNMENT_RE.search(value))
    ):
        raise HttpConnectorConfigError(
            f"{path} appears to contain a secret; use the API key field"
        )


def _canonical_synthesis_body(raw: Mapping[str, Any], *, content_type: str) -> Any:
    # Canonical `body` wins. Older UI aliases are accepted only when body is
    # absent, then normalized by the settings service before persistence.
    if "body" in raw:
        value = raw.get("body")
    elif "body_template" in raw:
        value = raw.get("body_template")
    else:
        value = raw.get("request_template", {})
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            value = {}
        else:
            try:
                value = json.loads(cleaned)
            except (json.JSONDecodeError, RecursionError) as exc:
                raise HttpConnectorConfigError(
                    "http_connector.synthesis.body must be valid JSON"
                ) from exc
    if content_type == "application/json" and not isinstance(value, (dict, list)):
        raise HttpConnectorConfigError(
            "http_connector.synthesis.body must be a JSON object or array"
        )
    if content_type == "application/x-www-form-urlencoded" and not isinstance(value, dict):
        raise HttpConnectorConfigError(
            "http_connector.synthesis.body must be an object for form encoding"
        )
    return _validate_template(value, field_name="http_connector.synthesis.body")


def _canonical_polling_body(
    raw: Mapping[str, Any],
    *,
    method: str,
    content_type: str,
) -> Any:
    if "body" in raw:
        value = raw.get("body")
    elif "body_template" in raw:
        value = raw.get("body_template")
    else:
        value = raw.get("request_template", {})
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            value = {}
        else:
            try:
                value = json.loads(cleaned)
            except (json.JSONDecodeError, RecursionError) as exc:
                raise HttpConnectorConfigError(
                    "http_connector.synthesis.polling.body must be valid JSON"
                ) from exc
    if method == "GET":
        if value not in (None, {}, []):
            raise HttpConnectorConfigError(
                "http_connector.synthesis.polling.body requires POST or PUT"
            )
        return {}
    if content_type == "application/json" and not isinstance(value, (dict, list)):
        raise HttpConnectorConfigError(
            "http_connector.synthesis.polling.body must be a JSON object or array"
        )
    if content_type == "application/x-www-form-urlencoded" and not isinstance(value, dict):
        raise HttpConnectorConfigError(
            "http_connector.synthesis.polling.body must be an object for form encoding"
        )
    return _validate_template(
        value,
        field_name="http_connector.synthesis.polling.body",
    )


def _canonical_catalog_body(
    raw: Mapping[str, Any],
    *,
    method: str,
    content_type: str,
) -> Any:
    value = raw.get("body", raw.get("body_template", raw.get("request_template", {})))
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            value = {}
        else:
            try:
                value = json.loads(cleaned)
            except (json.JSONDecodeError, RecursionError) as exc:
                raise HttpConnectorConfigError(
                    "catalog request body must be valid JSON"
                ) from exc
    if method == "GET":
        if value not in (None, {}, []):
            raise HttpConnectorConfigError("catalog request body requires POST or PUT")
        return {}
    if content_type == "application/json" and not isinstance(value, (dict, list)):
        raise HttpConnectorConfigError(
            "catalog request body must be a JSON object or array"
        )
    if content_type == "application/x-www-form-urlencoded" and not isinstance(value, dict):
        raise HttpConnectorConfigError(
            "catalog request body must be an object for form encoding"
        )
    validated = _validate_template(value, field_name="catalog request body")
    if _PLACEHOLDER_RE.search(json.dumps(validated, ensure_ascii=False)):
        raise HttpConnectorConfigError(
            "catalog request body cannot contain runtime placeholders"
        )
    return validated


def _parse_catalog_resource(raw: Any, *, resource: str) -> HttpConnectorCatalogResource | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        raw = {"path": raw}
    if not isinstance(raw, Mapping):
        raise HttpConnectorConfigError(f"catalog.{resource} must be an object")
    # The UI sends empty resource blocks while a connector is being drafted;
    # treat those as omitted so the operator can still use manual IDs.
    if not str(raw.get("path") or raw.get("endpoint") or "").strip():
        return None
    method = str(raw.get("method") or "GET").strip().upper()
    if method not in {"GET", "POST", "PUT"}:
        raise HttpConnectorConfigError(
            f"catalog.{resource}.method must be GET, POST or PUT"
        )
    content_type = str(
        raw.get("content_type") or raw.get("contentType") or "application/json"
    ).strip().lower()
    if content_type not in {
        "application/json",
        "application/x-www-form-urlencoded",
    }:
        raise HttpConnectorConfigError(
            f"catalog.{resource}.content_type is unsupported"
        )
    return HttpConnectorCatalogResource(
        path=_clean_endpoint(
            raw.get("path") or raw.get("endpoint"),
            field_name=f"catalog.{resource}.path",
            required=True,
        ),
        method=method,
        content_type=content_type,
        body=_canonical_catalog_body(
            raw,
            method=method,
            content_type=content_type,
        ),
        items_path=_clean_json_path(
            raw.get("items_path") if "items_path" in raw else raw.get("itemsPath"),
            field_name=f"catalog.{resource}.items_path",
        ),
        id_path=_clean_json_path(
            raw.get("id_path") if "id_path" in raw else raw.get("idPath"),
            field_name=f"catalog.{resource}.id_path",
            default="code" if resource == "languages" else "id",
        ),
        label_path=_clean_json_path(
            raw.get("label_path") if "label_path" in raw else raw.get("labelPath"),
            field_name=f"catalog.{resource}.label_path",
            default="name",
        ),
        languages_path=_clean_json_path(
            raw.get("languages_path") if "languages_path" in raw else raw.get("languagesPath"),
            field_name=f"catalog.{resource}.languages_path",
        ),
        models_path=_clean_json_path(
            raw.get("models_path") if "models_path" in raw else raw.get("modelsPath"),
            field_name=f"catalog.{resource}.models_path",
        ),
        voices_path=_clean_json_path(
            raw.get("voices_path") if "voices_path" in raw else raw.get("voicesPath"),
            field_name=f"catalog.{resource}.voices_path",
        ),
        gender_path=_clean_json_path(
            raw.get("gender_path") if "gender_path" in raw else raw.get("genderPath"),
            field_name=f"catalog.{resource}.gender_path",
        ),
        description_path=_clean_json_path(
            raw.get("description_path")
            if "description_path" in raw
            else raw.get("descriptionPath"),
            field_name=f"catalog.{resource}.description_path",
        ),
        capabilities_path=_clean_json_path(
            raw.get("capabilities_path")
            if "capabilities_path" in raw
            else raw.get("capabilitiesPath"),
            field_name=f"catalog.{resource}.capabilities_path",
        ),
    )


def _parse_response(raw: Any) -> HttpConnectorResponse:
    if raw is None:
        raw = {}
    if isinstance(raw, str):
        raw = {"type": raw}
    if not isinstance(raw, Mapping):
        raise HttpConnectorConfigError("synthesis.response must be an object")
    response_type = str(raw.get("type") or "binary").strip().lower()
    if response_type == "audio_binary":
        response_type = "binary"
    if response_type not in {"binary", "json_base64", "json_url", "async_json"}:
        raise HttpConnectorConfigError("synthesis.response.type is unsupported")
    mime_type = str(raw.get("mime_type") or raw.get("mimeType") or "").strip().lower()
    if mime_type and not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", mime_type):
        raise HttpConnectorConfigError("synthesis.response.mime_type is invalid")
    file_extension = str(
        raw.get("file_extension") or raw.get("fileExtension") or ""
    ).strip().lstrip(".").lower()
    if file_extension and not re.fullmatch(r"[a-z0-9]{1,10}", file_extension):
        raise HttpConnectorConfigError("synthesis.response.file_extension is invalid")
    return HttpConnectorResponse(
        type=response_type,
        audio_path=_clean_json_path(raw.get("audio_path") or raw.get("audioPath"), field_name="synthesis.response.audio_path"),
        mime_type=mime_type,
        mime_type_path=_clean_json_path(
            raw.get("mime_type_path") or raw.get("mimeTypePath"),
            field_name="synthesis.response.mime_type_path",
        ),
        duration_path=_clean_json_path(
            raw.get("duration_path") or raw.get("durationPath"),
            field_name="synthesis.response.duration_path",
        ),
        file_extension=file_extension,
    )


def _parse_polling(raw: Any) -> HttpConnectorPolling | None:
    if raw in (None, ""):
        return None
    if not isinstance(raw, Mapping):
        raise HttpConnectorConfigError("synthesis.polling must be an object")
    method = str(
        raw.get("method") or raw.get("poll_method") or raw.get("pollMethod") or "GET"
    ).strip().upper()
    if method not in {"GET", "POST", "PUT"}:
        raise HttpConnectorConfigError(
            "synthesis.polling.method must be GET, POST or PUT"
        )
    content_type = str(
        raw.get("content_type")
        or raw.get("contentType")
        or "application/json"
    ).strip().lower()
    if content_type not in {
        "application/json",
        "application/x-www-form-urlencoded",
    }:
        raise HttpConnectorConfigError(
            "synthesis.polling.content_type is unsupported"
        )
    try:
        interval = float(raw.get("interval_seconds") or raw.get("intervalSeconds") or 1.0)
        attempts = int(raw.get("max_attempts") or raw.get("maxAttempts") or 30)
    except (TypeError, ValueError) as exc:
        raise HttpConnectorConfigError("synthesis.polling bounds are invalid") from exc
    if not math.isfinite(interval):
        raise HttpConnectorConfigError("synthesis.polling bounds are invalid")
    interval = max(0.1, min(interval, CONNECTOR_POLL_MAX_INTERVAL_SECONDS))
    attempts = max(1, min(attempts, CONNECTOR_POLL_MAX_ATTEMPTS))
    response_type = str(raw.get("response_type") or raw.get("responseType") or "json_url").strip().lower()
    if response_type not in {"binary", "json_base64", "json_url"}:
        raise HttpConnectorConfigError("synthesis.polling.response_type is unsupported")
    success = raw.get("success_values") or raw.get("successValues") or (
        "completed",
        "succeeded",
        "success",
        "done",
    )
    failure = raw.get("failure_values") or raw.get("failureValues") or (
        "failed",
        "error",
        "cancelled",
        "canceled",
    )
    if isinstance(success, str):
        success = [success]
    if isinstance(failure, str):
        failure = [failure]
    if not isinstance(success, Sequence) or not isinstance(failure, Sequence):
        raise HttpConnectorConfigError("synthesis.polling status values are invalid")
    return HttpConnectorPolling(
        job_id_path=_clean_json_path(
            raw.get("job_id_path") or raw.get("jobIdPath"),
            field_name="synthesis.polling.job_id_path",
            default="id",
        ),
        poll_path=_clean_endpoint(
            raw.get("poll_path") or raw.get("pollPath"),
            field_name="synthesis.polling.poll_path",
            required=True,
            allowed_placeholders=frozenset({"job_id"}),
        ),
        method=method,
        content_type=content_type,
        body=_canonical_polling_body(
            raw,
            method=method,
            content_type=content_type,
        ),
        status_path=_clean_json_path(
            raw.get("status_path") or raw.get("statusPath"),
            field_name="synthesis.polling.status_path",
            default="status",
        ),
        success_values=tuple(str(item).strip().casefold() for item in success if str(item).strip())[:20],
        failure_values=tuple(str(item).strip().casefold() for item in failure if str(item).strip())[:20],
        interval_seconds=interval,
        max_attempts=attempts,
        response_type=response_type,
        audio_path=_clean_json_path(
            raw.get("audio_path") or raw.get("audioPath"),
            field_name="synthesis.polling.audio_path",
        ),
        mime_type_path=_clean_json_path(
            raw.get("mime_type_path") or raw.get("mimeTypePath"),
            field_name="synthesis.polling.mime_type_path",
        ),
        duration_path=_clean_json_path(
            raw.get("duration_path") or raw.get("durationPath"),
            field_name="synthesis.polling.duration_path",
        ),
    )


def parse_http_connector_manifest(options: Any) -> HttpConnectorManifest | None:
    """Validate and normalize ``options_json.http_connector``.

    ``options`` may be either the whole options object or the nested manifest,
    which keeps unit tests and internal call sites simple.
    """

    if not isinstance(options, Mapping):
        return None
    raw: Any = options.get(HTTP_CONNECTOR_OPTION_KEY, options)
    if HTTP_CONNECTOR_OPTION_KEY in options and not isinstance(raw, Mapping):
        raise HttpConnectorConfigError("http_connector must be an object")
    if not isinstance(raw, Mapping) or not raw:
        return None
    _reject_manifest_secrets(raw)
    try:
        version = int(raw.get("version") or HTTP_CONNECTOR_VERSION)
    except (TypeError, ValueError) as exc:
        raise HttpConnectorConfigError("http_connector.version is invalid") from exc
    if version != HTTP_CONNECTOR_VERSION:
        raise HttpConnectorConfigError(
            f"Unsupported http_connector version {version}; expected {HTTP_CONNECTOR_VERSION}"
        )
    mode = str(raw.get("mode") or "auto").strip().lower()
    if mode not in {"auto", "openapi", "custom"}:
        raise HttpConnectorConfigError("http_connector.mode is unsupported")

    auth_raw = raw.get("auth") or {}
    if not isinstance(auth_raw, Mapping):
        raise HttpConnectorConfigError("http_connector.auth must be an object")
    auth_type = str(auth_raw.get("type") or auth_raw.get("scheme") or "bearer").strip().lower()
    if auth_type not in {"none", "bearer", "header", "query"}:
        raise HttpConnectorConfigError("http_connector.auth.type is unsupported")
    default_header = "Authorization" if auth_type == "bearer" else "X-API-Key"
    default_prefix = "Bearer " if auth_type == "bearer" else ""
    prefix = str(auth_raw.get("prefix") if auth_raw.get("prefix") is not None else default_prefix)
    if (
        len(prefix) > 80
        or any(char in prefix for char in "\r\n")
        or any(ord(char) < 0x20 or ord(char) > 0x7E for char in prefix)
    ):
        raise HttpConnectorConfigError("http_connector.auth.prefix is invalid")
    query_name = str(auth_raw.get("query_name") or auth_raw.get("queryName") or "api_key").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.~-]{1,80}", query_name):
        raise HttpConnectorConfigError("http_connector.auth.query_name is invalid")
    test_method = str(auth_raw.get("test_method") or auth_raw.get("testMethod") or "GET").strip().upper()
    if test_method not in {"GET", "HEAD"}:
        raise HttpConnectorConfigError("http_connector.auth.test_method is unsupported")
    auth_header_name = _clean_header_name(
        auth_raw.get("header_name") or auth_raw.get("headerName") or auth_raw.get("header"),
        field_name="http_connector.auth.header_name",
        default=default_header,
    )
    if auth_header_name.casefold() in {
        "host",
        "content-length",
        "content-type",
        "accept",
        "user-agent",
        "cookie",
        "proxy-authorization",
        "connection",
        "transfer-encoding",
        "upgrade",
    }:
        raise HttpConnectorConfigError("http_connector.auth.header_name is not allowed")
    auth = HttpConnectorAuth(
        type=auth_type,
        header_name=auth_header_name,
        prefix=prefix,
        query_name=query_name,
        test_path=_clean_endpoint(
            auth_raw.get("test_path") or auth_raw.get("testPath"),
            field_name="http_connector.auth.test_path",
        ),
        test_method=test_method,
    )

    openapi_raw = raw.get("openapi") or {}
    if isinstance(openapi_raw, str):
        openapi_raw = {"url": openapi_raw}
    if not isinstance(openapi_raw, Mapping):
        raise HttpConnectorConfigError("http_connector.openapi must be an object")
    if not openapi_raw.get("url") and raw.get("openapi_url"):
        openapi_raw = {**dict(openapi_raw), "url": raw.get("openapi_url")}
    openapi = HttpConnectorOpenApi(
        url=_clean_endpoint(
            openapi_raw.get("url") or openapi_raw.get("discovery_url"),
            field_name="http_connector.openapi.url",
        )
    )
    if mode == "openapi" and not openapi.url:
        raise HttpConnectorConfigError("http_connector.openapi.url is required in openapi mode")

    catalog_raw = raw.get("catalog") or raw.get("discovery") or {}
    if not isinstance(catalog_raw, Mapping):
        raise HttpConnectorConfigError("http_connector.catalog must be an object")
    catalog = HttpConnectorCatalog(
        models=_parse_catalog_resource(catalog_raw.get("models"), resource="models"),
        voices=_parse_catalog_resource(catalog_raw.get("voices"), resource="voices"),
        languages=_parse_catalog_resource(catalog_raw.get("languages"), resource="languages"),
    )

    synthesis_raw = raw.get("synthesis")
    synthesis: HttpConnectorSynthesis | None = None
    if isinstance(synthesis_raw, Mapping) and not synthesis_raw:
        synthesis_raw = None
    if isinstance(synthesis_raw, Mapping) and not str(
        synthesis_raw.get("path") or synthesis_raw.get("endpoint") or ""
    ).strip():
        if synthesis_raw.get("body", synthesis_raw.get("body_template", {})) in (None, "", {}) and not synthesis_raw.get("polling"):
            synthesis_raw = None
        else:
            raise HttpConnectorConfigError("http_connector.synthesis.path is required when configured")
    if synthesis_raw not in (None, ""):
        if not isinstance(synthesis_raw, Mapping):
            raise HttpConnectorConfigError("http_connector.synthesis must be an object")
        method = str(synthesis_raw.get("method") or "POST").strip().upper()
        if method not in {"POST", "PUT"}:
            raise HttpConnectorConfigError("http_connector.synthesis.method must be POST or PUT")
        content_type = str(
            synthesis_raw.get("content_type")
            or synthesis_raw.get("contentType")
            or "application/json"
        ).strip().lower()
        if content_type not in {"application/json", "application/x-www-form-urlencoded"}:
            raise HttpConnectorConfigError("http_connector.synthesis.content_type is unsupported")
        headers_raw = synthesis_raw.get("headers") or {}
        if not isinstance(headers_raw, Mapping) or len(headers_raw) > 30:
            raise HttpConnectorConfigError("http_connector.synthesis.headers is invalid")
        headers: dict[str, str] = {}
        for key, value in headers_raw.items():
            name = _clean_header_name(
                key,
                field_name="http_connector.synthesis.headers",
                default="X-Connector-Header",
            )
            if (
                name.casefold()
                in {
                    "authorization",
                    "proxy-authorization",
                    "cookie",
                    "host",
                    "content-length",
                    "content-type",
                    "accept",
                    "user-agent",
                    "connection",
                    "transfer-encoding",
                    "upgrade",
                    "te",
                    "trailer",
                }
                or _SECRET_KEY_RE.search(name)
                or re.search(r"(?i)(api[-_]?key|token|secret)", name)
            ):
                raise HttpConnectorConfigError(
                    f"http_connector.synthesis.headers cannot set {name}"
                )
            rendered = str(_validate_template(str(value), field_name="http_connector.synthesis.headers"))
            if any(match.group(1).lower() == "text" for match in _PLACEHOLDER_RE.finditer(rendered)):
                raise HttpConnectorConfigError(
                    "http_connector.synthesis.headers cannot interpolate text"
                )
            headers[name] = rendered
        response_raw = synthesis_raw.get("response") or {}
        if not isinstance(response_raw, Mapping) or not response_raw:
            response_raw = {
                "type": synthesis_raw.get("response_type")
                or synthesis_raw.get("responseType"),
                "audio_path": synthesis_raw.get("audio_path")
                or synthesis_raw.get("audioPath"),
                "mime_type": synthesis_raw.get("mime_type")
                or synthesis_raw.get("mimeType"),
                "mime_type_path": synthesis_raw.get("mime_type_path")
                or synthesis_raw.get("mimeTypePath"),
                "duration_path": synthesis_raw.get("duration_path")
                or synthesis_raw.get("durationPath"),
                "file_extension": synthesis_raw.get("file_extension")
                or synthesis_raw.get("fileExtension"),
            }
        polling_raw = synthesis_raw.get("polling")
        if isinstance(response_raw, Mapping) and polling_raw is None:
            polling_raw = response_raw.get("polling")
        if polling_raw is None and str(response_raw.get("type") or "").strip().lower() == "async_json":
            polling_raw = {
                "job_id_path": synthesis_raw.get("job_id_path"),
                "poll_path": synthesis_raw.get("poll_path_template") or synthesis_raw.get("poll_path"),
                "status_path": synthesis_raw.get("status_path"),
                "success_values": synthesis_raw.get("success_values"),
                "failure_values": synthesis_raw.get("failure_values"),
            }
        synthesis = HttpConnectorSynthesis(
            path=_clean_endpoint(
                synthesis_raw.get("path") or synthesis_raw.get("endpoint"),
                field_name="http_connector.synthesis.path",
                required=True,
                allowed_placeholders=frozenset({"model_id", "voice_id", "language_code"}),
            ),
            method=method,
            content_type=content_type,
            body=_canonical_synthesis_body(synthesis_raw, content_type=content_type),
            headers=headers,
            response=_parse_response(response_raw),
            polling=_parse_polling(polling_raw),
        )
        if synthesis.response.type == "async_json" and synthesis.polling is None:
            raise HttpConnectorConfigError(
                "http_connector.synthesis.polling is required for async_json"
            )

    return HttpConnectorManifest(
        version=version,
        mode=mode,
        auth=auth,
        openapi=openapi,
        catalog=catalog,
        synthesis=synthesis,
    )


def http_connector_config_fingerprint(
    manifest: HttpConnectorManifest,
    *,
    provider: str,
    base_url: str,
    api_key: str | None = None,
) -> str:
    """Hash public configuration plus a non-reversible credential hint.

    The hint contains only whether a key is set, its length, and its final four
    characters (the latter is already shown by the masked Ops field).  The raw
    credential is never serialized or returned.
    """

    payload = {
        "provider": str(provider or "").strip().lower(),
        "base_url": str(base_url or "").strip().rstrip("/"),
        "credential_hint": {
            "set": bool(api_key),
            "length": len(api_key or ""),
            "last4": str(api_key or "")[-4:] if api_key else "",
        },
        "manifest": asdict(manifest),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def redact_http_connector_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Defense-in-depth redaction for legacy manifests returned by public APIs."""

    def _redact(value: Any, key: str = "", depth: int = 0) -> Any:
        if depth > CONNECTOR_MAX_MANIFEST_DEPTH:
            return ""
        if _SECRET_KEY_RE.search(key) and key.casefold() not in {"query_name", "header_name"}:
            return ""
        if isinstance(value, Mapping):
            return {
                str(item_key): _redact(item, str(item_key), depth + 1)
                for item_key, item in value.items()
            }
        if isinstance(value, list):
            return [_redact(item, key, depth + 1) for item in value]
        if isinstance(value, str) and (
            _EMBEDDED_SECRET_RE.search(value) or _SECRET_ASSIGNMENT_RE.search(value)
        ):
            return ""
        if isinstance(value, str) and "?" in value:
            try:
                parsed_url = urllib.parse.urlsplit(value)
                query = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
            except ValueError:
                query = []
                parsed_url = None
            if parsed_url is not None and any(_QUERY_SECRET_KEY_RE.search(key) for key, _ in query):
                # Keep only the endpoint path; never expose a legacy query
                # credential through the public options payload.
                return urllib.parse.urlunsplit(
                    (parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "")
                )
        if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError, RecursionError):
                parsed = None
            if isinstance(parsed, (dict, list)):
                return json.dumps(
                    _redact(parsed, key, depth + 1),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        return value

    output = dict(options)
    connector = output.get(HTTP_CONNECTOR_OPTION_KEY)
    if isinstance(connector, Mapping):
        cleaned_connector = _redact(connector)
        synthesis = cleaned_connector.get("synthesis") if isinstance(cleaned_connector, dict) else None
        if isinstance(synthesis, dict) and "body" in synthesis:
            synthesis.pop("body_template", None)
            synthesis.pop("request_template", None)
        output[HTTP_CONNECTOR_OPTION_KEY] = cleaned_connector
    elif HTTP_CONNECTOR_OPTION_KEY in output:
        # Legacy malformed values may contain arbitrary text, including a
        # credential. Never return them through the public settings API.
        output.pop(HTTP_CONNECTOR_OPTION_KEY, None)
    return output


def normalize_http_connector_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return storage-safe options with legacy request-template aliases removed."""

    output = dict(options)
    connector_raw = output.get(HTTP_CONNECTOR_OPTION_KEY)
    if HTTP_CONNECTOR_OPTION_KEY not in output:
        return output
    if not isinstance(connector_raw, Mapping):
        raise HttpConnectorConfigError("http_connector must be an object")
    connector = dict(connector_raw)
    synthesis_raw = connector.get("synthesis")
    if isinstance(synthesis_raw, Mapping):
        synthesis = dict(synthesis_raw)
        if "body" not in synthesis:
            alias = synthesis.get("body_template", synthesis.get("request_template"))
            if alias is not None:
                content_type = str(
                    synthesis.get("content_type")
                    or synthesis.get("contentType")
                    or "application/json"
                ).strip().lower()
                synthesis["body"] = _canonical_synthesis_body(
                    synthesis,
                    content_type=content_type,
                )
        synthesis.pop("body_template", None)
        synthesis.pop("request_template", None)
        connector["synthesis"] = synthesis
    output[HTTP_CONNECTOR_OPTION_KEY] = connector
    # Validation also scans ignored/unknown fields for secret material.
    parse_http_connector_manifest(output)
    return output


def normalize_connector_api_key(raw: str | None) -> tuple[str, list[str]]:
    """Normalize a commonly pasted ``Bearer <token>`` without duplicating it."""

    value = str(raw or "").strip()
    if (
        len(value) > 4096
        or any(char in value for char in "\r\n\0")
        or any(ord(char) > 0x7F for char in value)
    ):
        raise HttpConnectorConfigError("API key contains invalid characters or is too long")
    warnings: list[str] = []
    match = re.match(r"(?i)^bearer\s+(.+)$", value)
    if match:
        value = match.group(1).strip()
        warnings.append("Removed the optional Bearer prefix from the API key input.")
        if re.match(r"(?i)^bearer\s+", value):
            raise HttpConnectorConfigError(
                "API key contains a duplicate Bearer prefix; enter only the raw token"
            )
    return value, warnings


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").rstrip(".").lower()
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise HttpConnectorRequestError("invalid_url") from exc
    return scheme, host, port


def _validate_public_host(hostname: str, port: int, resolver: Resolver) -> None:
    host = hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise HttpConnectorRequestError("ssrf_blocked")
    try:
        rows = resolver(host, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise HttpConnectorRequestError("dns_failed") from exc
    addresses = []
    for row in rows:
        try:
            addresses.append(ipaddress.ip_address(str(row[4][0]).split("%", 1)[0]))
        except (IndexError, TypeError, ValueError):
            continue
    if not addresses:
        raise HttpConnectorRequestError("dns_failed")
    if any(not address.is_global for address in addresses):
        raise HttpConnectorRequestError("ssrf_blocked")


def _normalize_base_url(
    raw: str,
    *,
    has_credentials: bool,
    require_https: bool = False,
    resolver: Resolver,
) -> str:
    value = str(raw or "").strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise HttpConnectorRequestError("invalid_base_url") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise HttpConnectorRequestError("invalid_base_url")
    if (has_credentials or require_https) and parsed.scheme.lower() != "https":
        raise HttpConnectorRequestError("insecure_credentials")
    decoded_path = urllib.parse.unquote(parsed.path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise HttpConnectorRequestError("invalid_base_url")
    resolved_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    _validate_public_host(parsed.hostname, resolved_port, resolver)
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origin: tuple[str, str, int]):
        super().__init__()
        self.allowed_origin = allowed_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, PLR0913
        parsed = urllib.parse.urlsplit(newurl)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(
                segment in {".", ".."}
                for segment in urllib.parse.unquote(parsed.path).split("/")
            )
        ):
            raise HttpConnectorRequestError("invalid_redirect")
        if _origin(newurl) != self.allowed_origin:
            raise HttpConnectorRequestError("cross_origin_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SafeHttpConnectorTransport:
    """Same-origin request transport with a shared deadline and size bounds."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        auth: HttpConnectorAuth,
        timeout_seconds: float,
        max_response_bytes: int,
        require_https: bool = False,
        opener: OpenFunction | None = None,
        resolver: Resolver = socket.getaddrinfo,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key, self.key_warnings = normalize_connector_api_key(api_key)
        self.auth = auth
        has_credentials = bool(self.api_key and auth.type != "none")
        self.base_url = _normalize_base_url(
            base_url,
            has_credentials=has_credentials,
            require_https=require_https,
            resolver=resolver,
        )
        self.origin = _origin(self.base_url)
        self._deadline = monotonic() + max(0.1, float(timeout_seconds))
        self._monotonic = monotonic
        self._max_response_bytes = max(1, int(max_response_bytes))
        self._resolver = resolver
        if opener is None:
            director = urllib.request.build_opener(_SameOriginRedirectHandler(self.origin))
            self._open: OpenFunction = director.open
        else:
            self._open = opener
        self.endpoints: list[str] = []

    def _resolve_endpoint(self, endpoint: str) -> str:
        value = _clean_endpoint(endpoint, field_name="endpoint", required=True)
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme:
            if _origin(value) != self.origin:
                raise HttpConnectorRequestError("cross_origin_endpoint")
            url = value
        else:
            path = "/" + value.lstrip("/")
            base = urllib.parse.urlsplit(self.base_url)
            base_path = base.path.rstrip("/")
            # OpenAPI documents often expose absolute API paths (/v1/models).
            # Avoid duplicating the base path when it is already present.
            if base_path and (path == base_path or path.startswith(base_path + "/")):
                url = urllib.parse.urlunsplit((base.scheme, base.netloc, path, "", ""))
            else:
                url = self.base_url + path
        if _origin(url) != self.origin:
            raise HttpConnectorRequestError("cross_origin_endpoint")
        return url

    def request(
        self,
        endpoint: str,
        *,
        method: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        accept: str = "application/json",
    ) -> _HttpResponse:
        remaining = self._deadline - self._monotonic()
        if remaining <= 0:
            raise HttpConnectorRequestError("deadline_exceeded")
        url = self._resolve_endpoint(endpoint)
        auth_headers: dict[str, str] = {}
        if self.api_key and self.auth.type in {"bearer", "header"}:
            auth_headers[self.auth.header_name] = f"{self.auth.prefix}{self.api_key}"
        if self.api_key and self.auth.type == "query":
            split = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qsl(split.query, keep_blank_values=True)
            query.append((self.auth.query_name, self.api_key))
            url = urllib.parse.urlunsplit(
                (split.scheme, split.netloc, split.path, urllib.parse.urlencode(query), "")
            )
        endpoint_path = urllib.parse.urlsplit(url).path
        if endpoint_path not in self.endpoints:
            self.endpoints.append(endpoint_path)
        request_headers = {
            "Accept": accept,
            "User-Agent": "reup-douyin-universal-tts/1",
            **auth_headers,
            **dict(headers or {}),
        }
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with self._open(request, timeout=max(0.05, remaining)) as response:
                status = int(getattr(response, "status", None) or response.getcode() or 200)
                raw = response.read(self._max_response_bytes + 1) if method != "HEAD" else b""
                content_type = str(response.headers.get("Content-Type") or "") if hasattr(response, "headers") else ""
        except HttpConnectorRequestError:
            raise
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read(CONNECTOR_PROVIDER_ERROR_MAX_BYTES + 1)
            except (OSError, ValueError):
                error_body = b""
            raise HttpConnectorRequestError(
                f"http_{exc.code}",
                http_status=int(exc.code),
                provider_detail=_provider_error_detail(error_body),
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise HttpConnectorRequestError("timeout") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise HttpConnectorRequestError("connection_error") from exc
        if status < 200 or status >= 300:
            raise HttpConnectorRequestError(f"http_{status}", http_status=status)
        if len(raw) > self._max_response_bytes:
            raise HttpConnectorRequestError("response_too_large")
        return _HttpResponse(status=status, body=raw, content_type=content_type)

    def request_json(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        content_type: str = "application/json",
        body: Any = None,
    ) -> tuple[Any, int]:
        encoded_body: bytes | None = None
        headers: dict[str, str] = {}
        if method not in {"GET", "HEAD"}:
            if content_type == "application/json":
                encoded_body = json.dumps(
                    body if body is not None else {},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            else:
                if not isinstance(body, Mapping):
                    raise HttpConnectorRequestError("invalid_request_body")
                encoded_body = urllib.parse.urlencode(
                    {str(key): str(value) for key, value in body.items()}
                ).encode("utf-8")
            headers["Content-Type"] = content_type
        response = self.request(
            endpoint,
            method=method,
            headers=headers,
            body=encoded_body,
            accept="application/json",
        )
        if method == "HEAD" or not response.body:
            return {}, response.status
        try:
            return json.loads(response.body.decode("utf-8")), response.status
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise HttpConnectorRequestError("invalid_json") from exc


def _json_path_parts(path: str) -> list[str]:
    cleaned = (path or "").strip()
    if cleaned in {"", "$"}:
        return []
    if cleaned.startswith("$."):
        cleaned = cleaned[2:]
    cleaned = cleaned.replace("[", ".").replace("]", "")
    return [part for part in cleaned.split(".") if part]


def json_path_get(payload: Any, path: str, default: Any = None) -> Any:
    """Read a bounded dotted/indexed JSON path; no expressions or filters."""

    values = [payload]
    for part in _json_path_parts(path):
        next_values: list[Any] = []
        for value in values:
            if part == "*" and isinstance(value, list):
                next_values.extend(value)
            elif isinstance(value, Mapping) and part in value:
                next_values.append(value[part])
            elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                next_values.append(value[int(part)])
        if not next_values:
            return default
        values = next_values
    if not values:
        return default
    return values[0] if len(values) == 1 else values


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _safe_text(value: Any, *, secret: str, limit: int = 256) -> str:
    text = str(value or "").strip()[:limit]
    return "" if secret and secret in text else text


def _parse_mapped_rows(
    payload: Any,
    mapping: HttpConnectorCatalogResource,
    *,
    resource: str,
    secret: str,
) -> tuple[list[Any], str]:
    rows = json_path_get(payload, mapping.items_path, payload)
    if isinstance(rows, Mapping):
        # A very common shape when items_path is omitted.
        for candidate in (resource, "data", "items", "results"):
            candidate_rows = rows.get(candidate)
            if isinstance(candidate_rows, list):
                rows = candidate_rows
                break
    if not isinstance(rows, list):
        raise HttpConnectorRequestError("invalid_response")
    output: list[Any] = []
    for row in rows[:CONNECTOR_MAX_OPTIONS]:
        if isinstance(row, str):
            identifier = _safe_text(row, secret=secret)
            if identifier:
                output.append((identifier, identifier, row))
            continue
        if not isinstance(row, Mapping):
            continue
        identifier = _safe_text(json_path_get(row, mapping.id_path), secret=secret)
        if not identifier:
            continue
        label = _safe_text(json_path_get(row, mapping.label_path), secret=secret, limit=200) or identifier
        output.append((identifier, label, row))
    return output, resource


def _mapped_catalog_options(
    payload: Any,
    mapping: HttpConnectorCatalogResource,
    *,
    resource: str,
    secret: str,
) -> tuple[list[Any], list[TtsLanguageOption]]:
    rows, _ = _parse_mapped_rows(payload, mapping, resource=resource, secret=secret)
    languages_seen: dict[str, TtsLanguageOption] = {}
    output: list[Any] = []
    for identifier, label, raw in rows:
        row = raw if isinstance(raw, Mapping) else {}
        language_values = _as_list(json_path_get(row, mapping.languages_path)) if mapping.languages_path else []
        languages: list[str] = []
        for item in language_values:
            if isinstance(item, Mapping):
                code = _safe_text(item.get("code") or item.get("id") or item.get("locale"), secret=secret, limit=64)
                language_label = _safe_text(item.get("label") or item.get("name") or code, secret=secret, limit=160)
            else:
                code = _safe_text(item, secret=secret, limit=64)
                language_label = code
            if code and code not in languages:
                languages.append(code)
                languages_seen.setdefault(code, TtsLanguageOption(code=code, label=language_label or code))
        capabilities = [
            _safe_text(item, secret=secret, limit=120)
            for item in (_as_list(json_path_get(row, mapping.capabilities_path)) if mapping.capabilities_path else [])
        ]
        capabilities = [item for item in capabilities if item]
        description = _safe_text(
            json_path_get(row, mapping.description_path) if mapping.description_path else "",
            secret=secret,
            limit=500,
        ) or None
        if resource == "models":
            voices = [
                _safe_text(item, secret=secret)
                for item in (_as_list(json_path_get(row, mapping.voices_path)) if mapping.voices_path else [])
            ]
            output.append(
                TtsModelOption(
                    id=identifier,
                    label=label,
                    languages=languages,
                    voices=[item for item in voices if item],
                    description=description,
                    capabilities=capabilities,
                )
            )
        elif resource == "voices":
            models = [
                _safe_text(item, secret=secret)
                for item in (_as_list(json_path_get(row, mapping.models_path)) if mapping.models_path else [])
            ]
            gender = _safe_text(
                json_path_get(row, mapping.gender_path) if mapping.gender_path else "",
                secret=secret,
                limit=40,
            ) or None
            output.append(
                TtsVoiceOption(
                    id=identifier,
                    label=label,
                    languages=languages,
                    models=[item for item in models if item],
                    gender=gender,
                    description=description,
                    capabilities=capabilities,
                )
            )
        else:
            output.append(TtsLanguageOption(code=identifier, label=label))
    return output, list(languages_seen.values())


def _infer_openapi_paths(payload: Any) -> dict[str, str]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("paths"), Mapping):
        raise HttpConnectorRequestError("invalid_openapi")
    discovered: dict[str, tuple[int, str]] = {}
    keywords = {
        "models": ("models", "model list", "listmodels"),
        "voices": ("voices", "voice list", "listvoices"),
        "languages": ("languages", "language list", "listlanguages", "locales"),
    }
    for raw_path, path_item in payload["paths"].items():
        path = str(raw_path or "").strip()
        if not path or "{" in path or not isinstance(path_item, Mapping):
            continue
        operation = path_item.get("get")
        if not isinstance(operation, Mapping):
            continue
        haystack = " ".join(
            [
                path,
                str(operation.get("operationId") or ""),
                str(operation.get("summary") or ""),
                " ".join(str(tag) for tag in _as_list(operation.get("tags"))),
            ]
        ).casefold()
        for resource, terms in keywords.items():
            score = sum(3 if term in path.casefold() else 1 for term in terms if term in haystack)
            if score > discovered.get(resource, (0, ""))[0]:
                discovered[resource] = (score, path)
    return {resource: path for resource, (score, path) in discovered.items() if score > 0}


def _default_mapping(path: str, resource: str) -> HttpConnectorCatalogResource:
    return HttpConnectorCatalogResource(
        path=path,
        items_path="",
        id_path="code" if resource == "languages" else "id",
        label_path="name",
        languages_path="languages" if resource != "languages" else "",
        models_path="models" if resource == "voices" else "",
        voices_path="voices" if resource == "models" else "",
        gender_path="gender" if resource == "voices" else "",
        description_path="description",
        capabilities_path="capabilities",
    )


def _request_error_detail(resource: str, exc: HttpConnectorRequestError) -> str:
    if exc.http_status is not None:
        detail = f"{resource} returned HTTP {exc.http_status}."
        if exc.provider_detail:
            detail += f" Provider: {exc.provider_detail}"
        return detail
    messages = {
        "invalid_base_url": "Base URL must be a valid public HTTP(S) API URL.",
        "insecure_credentials": "HTTPS is required when credentials are configured.",
        "ssrf_blocked": "The endpoint resolves to a private or restricted address.",
        "dns_failed": "The endpoint host could not be resolved.",
        "cross_origin_endpoint": "The endpoint must use the same origin as Base URL.",
        "cross_origin_redirect": "The endpoint redirected to another origin.",
        "response_too_large": "The response exceeded the safe size limit.",
        "invalid_json": "The endpoint did not return valid JSON.",
        "invalid_response": "The response does not match the configured JSON paths.",
        "invalid_openapi": "The OpenAPI document has an unsupported shape.",
        "remote_json_error": "The provider returned a JSON error response; verify the API key, account access, and request mapping.",
        "empty_response": "The provider returned no mapped catalog items; verify the account has active resources and the configured JSON paths.",
        "deadline_exceeded": "The request deadline was exceeded.",
        "timeout": "The request timed out.",
        "connection_error": "The endpoint could not be reached.",
    }
    return f"{resource}: {messages.get(exc.code, 'The endpoint could not be read.')}"


def _clean_provider_error_fragment(value: Any, *, max_chars: int) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    text = " ".join(str(value).split()).strip()
    if not text:
        return ""
    text = _EMBEDDED_SECRET_RE.sub("[redacted]", text)
    return text[:max_chars]


def _provider_error_detail(raw: bytes) -> str:
    """Return only allowlisted provider error fields, with secret patterns redacted."""

    if not raw:
        return ""
    try:
        payload = json.loads(raw[:CONNECTOR_PROVIDER_ERROR_MAX_BYTES].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return ""

    node: Any = payload
    if isinstance(payload, Mapping):
        for key in ("detail", "error"):
            candidate = payload.get(key)
            if isinstance(candidate, (Mapping, str)):
                node = candidate
                break

    if isinstance(node, str):
        return _clean_provider_error_fragment(node, max_chars=CONNECTOR_PROVIDER_ERROR_MAX_CHARS)
    if not isinstance(node, Mapping):
        return ""

    identifiers: list[str] = []
    for key in ("code", "status", "type"):
        value = _clean_provider_error_fragment(node.get(key), max_chars=100)
        if value and re.fullmatch(r"[A-Za-z0-9_.:/ -]{1,100}", value) and value not in identifiers:
            identifiers.append(value)

    message = ""
    for key in ("message", "error_description", "description"):
        message = _clean_provider_error_fragment(
            node.get(key),
            max_chars=CONNECTOR_PROVIDER_ERROR_MAX_CHARS,
        )
        if message:
            break

    parts = identifiers[:2]
    if message and message not in parts:
        parts.append(message)
    return ": ".join(parts)[:CONNECTOR_PROVIDER_ERROR_MAX_CHARS]


def discover_http_connector_catalog(
    provider: str,
    *,
    base_url: str,
    api_key: str,
    language_code: str,
    timeout_seconds: float,
    manifest: HttpConnectorManifest,
    opener: OpenFunction | None = None,
    resolver: Resolver = socket.getaddrinfo,
    monotonic: Callable[[], float] = time.monotonic,
) -> TtsProviderCatalog:
    """Run optional auth check, OpenAPI inference, and mapped catalog GETs."""

    checks: list[dict[str, Any]] = []
    fingerprint = http_connector_config_fingerprint(
        manifest,
        provider=provider,
        base_url=base_url,
        api_key=None,
    )
    warnings: list[str] = []
    try:
        discovery_timeout = float(timeout_seconds or 8.0)
    except (TypeError, ValueError):
        discovery_timeout = 8.0
    if not math.isfinite(discovery_timeout) or discovery_timeout <= 0:
        discovery_timeout = 8.0
    try:
        transport = SafeHttpConnectorTransport(
            base_url=base_url,
            api_key=api_key,
            auth=manifest.auth,
            timeout_seconds=min(discovery_timeout, CONNECTOR_DISCOVERY_TIMEOUT_SECONDS),
            max_response_bytes=CONNECTOR_JSON_MAX_BYTES,
            opener=opener,
            resolver=resolver,
            monotonic=monotonic,
        )
        fingerprint = http_connector_config_fingerprint(
            manifest,
            provider=provider,
            base_url=base_url,
            api_key=transport.api_key,
        )
    except (HttpConnectorConfigError, HttpConnectorRequestError) as exc:
        code = getattr(exc, "code", "invalid_api_key")
        detail = _request_error_detail("Connection", exc) if isinstance(exc, HttpConnectorRequestError) else str(exc)
        checks.append({"stage": "authentication", "status": "failed", "detail": detail})
        return TtsProviderCatalog(
            source="none",
            warning=detail,
            default_language_code=language_code,
            capabilities=capabilities_for_provider(provider),
            discovery=TtsCatalogDiscovery(
                status="unavailable",
                endpoints=[],
                warnings=[detail],
                error_code=code,
                checks=checks,
                config_fingerprint=fingerprint,
            ),
        )

    warnings.extend(transport.key_warnings)
    if manifest.auth.test_path:
        try:
            _, status = transport.request_json(
                manifest.auth.test_path,
                method=manifest.auth.test_method,
            )
            checks.append(
                {
                    "stage": "authentication",
                    "status": "passed",
                    "detail": f"Authentication endpoint accepted the request (HTTP {status}).",
                    "endpoint": urllib.parse.urlsplit(manifest.auth.test_path).path or manifest.auth.test_path,
                    "http_status": status,
                }
            )
        except HttpConnectorRequestError as exc:
            detail = _request_error_detail("Authentication check", exc)
            checks.append(
                {
                    "stage": "authentication",
                    "status": "failed",
                    "detail": detail,
                    "endpoint": urllib.parse.urlsplit(manifest.auth.test_path).path or manifest.auth.test_path,
                    **({"http_status": exc.http_status} if exc.http_status is not None else {}),
                }
            )
            warnings.append(detail)
            return TtsProviderCatalog(
                source="none",
                warning=" ".join(dict.fromkeys(warnings)),
                default_language_code=language_code,
                capabilities=capabilities_for_provider(provider),
                discovery=TtsCatalogDiscovery(
                    status="unavailable",
                    endpoints=list(transport.endpoints),
                    warnings=list(dict.fromkeys(warnings)),
                    error_code="authentication_failed" if exc.http_status in {401, 403} else exc.code,
                    checks=checks,
                    config_fingerprint=fingerprint,
                ),
            )
    else:
        checks.append(
            {
                "stage": "authentication",
                "status": "skipped",
                "detail": "No separate authentication test endpoint is configured.",
            }
        )

    resource_mappings: dict[str, HttpConnectorCatalogResource | None] = {
        "models": manifest.catalog.models,
        "voices": manifest.catalog.voices,
        "languages": manifest.catalog.languages,
    }
    if (
        manifest.mode == "auto"
        and not manifest.openapi.url
        and not any(resource_mappings.values())
    ):
        # Keep the familiar generic probe behavior when the operator has not
        # supplied an OpenAPI document or custom mappings yet.
        resource_mappings = {
            "models": _default_mapping("/models", "models"),
            "voices": _default_mapping("/voices", "voices"),
            "languages": _default_mapping("/languages", "languages"),
        }
    if manifest.openapi.url and manifest.mode in {"auto", "openapi"}:
        try:
            openapi_payload, _ = transport.request_json(manifest.openapi.url, method="GET")
            inferred = _infer_openapi_paths(openapi_payload)
            for resource, path in inferred.items():
                if resource_mappings.get(resource) is None:
                    resource_mappings[resource] = _default_mapping(path, resource)
            checks.append(
                {
                    "stage": "openapi",
                    "status": "passed",
                    "detail": f"OpenAPI discovery found {len(inferred)} catalog endpoint(s).",
                    "endpoint": urllib.parse.urlsplit(manifest.openapi.url).path or manifest.openapi.url,
                }
            )
        except HttpConnectorRequestError as exc:
            detail = _request_error_detail("OpenAPI discovery", exc)
            warnings.append(detail)
            checks.append(
                {
                    "stage": "openapi",
                    "status": "failed",
                    "detail": detail,
                    "endpoint": urllib.parse.urlsplit(manifest.openapi.url).path or manifest.openapi.url,
                }
            )

    model_options: list[TtsModelOption] = []
    voices: list[TtsVoiceOption] = []
    languages: dict[str, TtsLanguageOption] = {}
    successes = 0
    configured = 0
    for resource in ("models", "voices", "languages"):
        mapping = resource_mappings.get(resource)
        if mapping is None:
            continue
        configured += 1
        try:
            payload, status = transport.request_json(
                mapping.path,
                method=mapping.method,
                content_type=mapping.content_type,
                body=mapping.body,
            )
            if isinstance(payload, Mapping) and any(
                payload.get(key) not in (None, "", [], {})
                for key in ("error", "errors")
            ):
                raise HttpConnectorRequestError("remote_json_error")
            options, related_languages = _mapped_catalog_options(
                payload,
                mapping,
                resource=resource,
                secret=transport.api_key,
            )
            if not options:
                raise HttpConnectorRequestError("empty_response")
            successes += 1
            for language in related_languages:
                languages.setdefault(language.code, language)
            if resource == "models":
                model_options.extend(options)
            elif resource == "voices":
                voices.extend(options)
            else:
                for language in options:
                    languages.setdefault(language.code, language)
            checks.append(
                {
                    "stage": f"catalog_{resource}",
                    "status": "passed",
                    "detail": f"Loaded {len(options)} {resource} option(s) (HTTP {status}).",
                    "endpoint": urllib.parse.urlsplit(mapping.path).path or mapping.path,
                    "http_status": status,
                }
            )
        except HttpConnectorRequestError as exc:
            detail = _request_error_detail(f"{resource.title()} catalog", exc)
            warnings.append(detail)
            checks.append(
                {
                    "stage": f"catalog_{resource}",
                    "status": "failed",
                    "detail": detail,
                    "endpoint": urllib.parse.urlsplit(mapping.path).path or mapping.path,
                    **({"http_status": exc.http_status} if exc.http_status is not None else {}),
                }
            )

    if configured == 0:
        warning = "No catalog endpoint mapping was configured or discovered from OpenAPI."
        warnings.append(warning)
        checks.append({"stage": "catalog", "status": "skipped", "detail": warning})
    else:
        checks.append(
            {
                "stage": "catalog",
                "status": "passed" if successes == configured else "partial" if successes else "failed",
                "detail": f"Loaded {successes} of {configured} configured catalog resource(s).",
            }
        )

    has_data = bool(model_options or voices or languages)
    status = "complete" if configured and successes == configured else "partial" if has_data else "unavailable"
    return TtsProviderCatalog(
        source="provider" if has_data else "none",
        voices=voices[:CONNECTOR_MAX_OPTIONS],
        models=[option.id for option in model_options[:CONNECTOR_MAX_OPTIONS]],
        model_options=model_options[:CONNECTOR_MAX_OPTIONS],
        languages=list(languages.values())[:CONNECTOR_MAX_OPTIONS],
        default_voice_id=voices[0].id if voices else "",
        default_model_id=model_options[0].id if model_options else "",
        default_language_code=(
            language_code
            if language_code in languages
            else next(iter(languages), language_code)
        ),
        warning=" ".join(dict.fromkeys(warnings)),
        capabilities=capabilities_for_provider(provider),
        discovery=TtsCatalogDiscovery(
            status=status,
            endpoints=list(transport.endpoints),
            warnings=list(dict.fromkeys(warnings)),
            error_code="" if has_data or configured == 0 else "catalog_failed",
            checks=checks,
            config_fingerprint=fingerprint,
        ),
    )


def _render_template(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, context) for item in value]
    if not isinstance(value, str):
        return value
    matches = list(_PLACEHOLDER_RE.finditer(value))
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return context.get(matches[0].group(1).lower(), "")
    return _PLACEHOLDER_RE.sub(
        lambda match: str(context.get(match.group(1).lower(), "")),
        value,
    )


def _build_execution_contract(synthesis: HttpConnectorSynthesis, request: TtsProviderInput) -> dict[str, Any]:
    """Prove which expressive fields a declarative provider actually consumes."""
    placeholders: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str):
            placeholders.update(
                match.group(1).lower() for match in _PLACEHOLDER_RE.finditer(value)
            )
        elif isinstance(value, Mapping):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    collect(synthesis.body)
    collect(synthesis.headers)
    collect(synthesis.path)
    applied: list[str] = []
    if "ssml_text" in placeholders and request.ssml_text:
        applied.extend(("ssml", "emotion", "pause", "emphasis"))
    if "audio_tags" in placeholders and request.audio_tags:
        applied.extend(("audio_tags", "emotion", "pace", "pause", "emphasis"))
    # Providers such as ElevenLabs receive canonical Audio Tags embedded in
    # the rendered text.  Merely having ``audio_tags`` on the request is not
    # proof that a plain ``{{text}}`` template consumed them: custom manifests
    # must either bind the explicit placeholder or pass a rendered string
    # that actually contains at least one requested tag.
    rendered_text_contains_tag = bool(
        request.audio_tags
        and request.text
        and any(str(tag).strip() and str(tag).strip() in request.text for tag in request.audio_tags)
    )
    if ({"text", "rendered_text"} & placeholders) and rendered_text_contains_tag:
        applied.extend(("audio_tags", "emotion", "pace", "pause", "emphasis"))
    if "voice_direction" in placeholders and request.voice_direction:
        applied.extend(("voice_direction", "pace"))
        direction = str(request.voice_direction).casefold()
        # The provider-neutral compiler emits these canonical fields into
        # voice_direction. Their presence proves that a manifest binding the
        # direction actually consumes the requested expressive controls.
        if "emotion " in direction:
            applied.append("emotion")
        if "pauses:" in direction or "pause before" in direction or "pause after" in direction:
            applied.append("pause")
        if "emphasize:" in direction and "emphasize: none" not in direction:
            applied.append("emphasis")
    if "sample_context" in placeholders and request.sample_context:
        applied.append("sample_context")
    if "speaking_rate" in placeholders:
        applied.append("speaking_rate")
    applied_set = set(applied)
    degraded: list[str] = []
    for feature in request.requested_features:
        if feature == "emotion" and not ("emotion" in applied_set):
            degraded.append("emotion_not_applied")
        elif feature == "pause" and not ("pause" in applied_set):
            degraded.append("pause_not_applied")
        elif feature == "emphasis" and not ("emphasis" in applied_set):
            degraded.append("emphasis_not_applied")
        elif feature == "pace" and not (
            "pace" in applied_set or "speaking_rate" in applied_set or "ssml" in applied_set
        ):
            degraded.append("pace_not_applied")
    return {
        "schema_version": "tts-provider-execution-contract-v1",
        "template_placeholders": sorted(placeholders),
        "requested_features": list(request.requested_features),
        "applied_features": sorted(applied_set),
        "degraded_features": list(dict.fromkeys(degraded)),
        "expressive_mode": request.expressive_mode,
    }


def _decode_json_audio(payload: Any, response_type: str, audio_path: str) -> tuple[bytes | None, str | None]:
    value = json_path_get(payload, audio_path)
    if not isinstance(value, str) or not value.strip():
        return None, None
    cleaned = value.strip()
    if response_type == "json_url":
        return None, cleaned
    if cleaned.startswith("data:") and "," in cleaned:
        cleaned = cleaned.split(",", 1)[1]
    try:
        audio = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HttpConnectorRequestError("invalid_audio_base64") from exc
    if not audio or len(audio) > CONNECTOR_AUDIO_MAX_BYTES:
        raise HttpConnectorRequestError("invalid_audio_size")
    return audio, None


def _download_public_audio_url(
    url: str,
    *,
    timeout_seconds: float,
    resolver: Resolver,
    opener: OpenFunction | None,
) -> _HttpResponse:
    if len(str(url or "").strip()) > 8192:
        raise HttpConnectorRequestError("invalid_audio_url")
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise HttpConnectorRequestError("invalid_audio_url") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise HttpConnectorRequestError("invalid_audio_url")
    _validate_public_host(parsed.hostname, port or 443, resolver)
    origin = _origin(url)
    if opener is None:
        open_fn: OpenFunction = urllib.request.build_opener(_SameOriginRedirectHandler(origin)).open
    else:
        open_fn = opener
    request = urllib.request.Request(
        url,
        headers={"Accept": "audio/*,application/octet-stream", "User-Agent": "reup-douyin-universal-tts/1"},
        method="GET",
    )
    try:
        with open_fn(request, timeout=max(0.1, min(timeout_seconds, CONNECTOR_SYNTHESIS_TIMEOUT_CAP_SECONDS))) as response:
            raw = response.read(CONNECTOR_AUDIO_MAX_BYTES + 1)
            status = int(getattr(response, "status", None) or response.getcode() or 200)
            content_type = str(response.headers.get("Content-Type") or "") if hasattr(response, "headers") else ""
    except HttpConnectorRequestError:
        raise
    except urllib.error.HTTPError as exc:
        raise HttpConnectorRequestError(f"http_{exc.code}", http_status=int(exc.code)) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise HttpConnectorRequestError("timeout") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise HttpConnectorRequestError("connection_error") from exc
    if status < 200 or status >= 300:
        raise HttpConnectorRequestError(f"http_{status}", http_status=status)
    if not raw or len(raw) > CONNECTOR_AUDIO_MAX_BYTES:
        raise HttpConnectorRequestError("invalid_audio_size")
    return _HttpResponse(status=status, body=raw, content_type=content_type)


def _guess_audio_metadata(audio: bytes, configured_mime: str, content_type: str, extension: str) -> tuple[str, str]:
    mime = (configured_mime or content_type or "").split(";", 1)[0].strip().lower()
    ext = extension.strip().lstrip(".").lower()
    if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
        mime, ext = mime or "audio/wav", ext or "wav"
    elif audio.startswith(b"ID3") or _has_mpeg_audio_signature(audio):
        mime, ext = mime or "audio/mpeg", ext or "mp3"
    elif audio.startswith(b"OggS"):
        mime, ext = mime or "audio/ogg", ext or "ogg"
    elif audio.startswith(b"fLaC"):
        mime, ext = mime or "audio/flac", ext or "flac"
    if not mime.startswith("audio/") and mime != "application/octet-stream":
        mime = "audio/mpeg"
    if not ext:
        ext = {"audio/wav": "wav", "audio/ogg": "ogg", "audio/flac": "flac"}.get(mime, "mp3")
    return mime, ext


def _has_known_audio_signature(audio: bytes) -> bool:
    return bool(
        (audio.startswith(b"RIFF") and audio[8:12] == b"WAVE")
        or audio.startswith(b"ID3")
        or _has_mpeg_audio_signature(audio)
        or audio.startswith(b"OggS")
        or audio.startswith(b"fLaC")
    )


def _has_mpeg_audio_signature(audio: bytes) -> bool:
    """Recognize MPEG audio frames even when the file has no ID3 tag.

    GenMax and other providers may return a valid MP3 stream whose first frame
    is an MPEG-2/2.5 variant (for example ``FF E3``) rather than the narrower
    ``FF FB``/``FF F3``/``FF F2`` prefixes. The sync mask avoids accepting
    textual JSON/HTML responses as audio while covering the valid MPEG layers.
    """
    return len(audio) >= 2 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0


def _looks_like_text_error_payload(audio: bytes) -> bool:
    """Detect obvious HTML/JSON error bodies returned from an audio URL."""
    sample = audio.lstrip()[:64].lower()
    return sample.startswith((b"<", b"{", b"[", b"error", b"unauthorized", b"forbidden"))


def _duration_seconds(audio: bytes, mime: str, supplied: Any, text: str, speaking_rate: float) -> float:
    try:
        value = float(supplied)
        if math.isfinite(value) and 0 < value <= 86_400:
            return value
    except (TypeError, ValueError):
        pass
    if mime == "audio/wav" or audio.startswith(b"RIFF"):
        try:
            with wave.open(BytesIO(audio), "rb") as wav:
                rate = wav.getframerate()
                if rate:
                    return wav.getnframes() / rate
        except (wave.Error, EOFError):
            pass
    try:
        normalized_rate = float(speaking_rate or 1.0)
    except (TypeError, ValueError):
        normalized_rate = 1.0
    if not math.isfinite(normalized_rate):
        normalized_rate = 1.0
    normalized_rate = max(0.5, min(normalized_rate, 2.0))
    return max(0.45, len(text.strip()) / (13.0 * normalized_rate))


class GenericHttpTtsProvider:
    """Synchronous TTS adapter driven exclusively by a validated manifest."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str | None,
        model_id: str,
        options: Mapping[str, Any],
        timeout_seconds: float,
        opener: OpenFunction | None = None,
        resolver: Resolver = socket.getaddrinfo,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        manifest = parse_http_connector_manifest(options)
        if manifest is None:
            raise HttpConnectorConfigError("options_json.http_connector is required")
        if manifest.synthesis is None:
            raise HttpConnectorConfigError("http_connector.synthesis is required for Preview")
        self.provider_name = provider_name
        self.base_url = base_url
        self.api_key = api_key or ""
        self.model_id = model_id
        self.manifest = manifest
        parsed_timeout = float(timeout_seconds or 120.0)
        if not math.isfinite(parsed_timeout):
            raise HttpConnectorConfigError("timeout_seconds must be finite")
        self.timeout_seconds = max(
            1.0,
            min(parsed_timeout, CONNECTOR_SYNTHESIS_TIMEOUT_CAP_SECONDS),
        )
        self._opener = opener
        self._resolver = resolver
        self._monotonic = monotonic
        self._sleeper = sleeper

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        synthesis = self.manifest.synthesis
        assert synthesis is not None
        try:
            speaking_rate = float(request.voice_config.speaking_rate or 1.0)
        except (TypeError, ValueError):
            speaking_rate = 1.0
        if not math.isfinite(speaking_rate):
            speaking_rate = 1.0
        speaking_rate = max(0.5, min(speaking_rate, 2.0))
        try:
            target_duration = float(request.target_duration_seconds or 0.0)
        except (TypeError, ValueError):
            target_duration = 0.0
        if not math.isfinite(target_duration) or target_duration <= 0:
            target_duration = 0.0
        context: dict[str, Any] = {
            "text": request.text,
            # ``text`` is the provider-safe rendered text (which may include
            # canonical Audio Tags for expressive providers). Keep an explicit
            # alias for connector manifests that want to document that intent.
            "rendered_text": request.text,
            "voice_direction": request.voice_direction or "",
            "sample_context": request.sample_context or "",
            "audio_tags": ", ".join(request.audio_tags),
            "ssml_text": request.ssml_text or "",
            "prosody_state": json.dumps(
                dict(request.prosody_state or {}),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "performance_chunk_id": request.performance_chunk_id or "",
            "model_id": self.model_id,
            "voice_id": request.voice_config.voice_id,
            "language_code": request.language_code or request.voice_config.language_code,
            "speaking_rate": speaking_rate,
            "target_duration_seconds": target_duration or "",
            "job_id": "",
        }
        try:
            execution_contract = _build_execution_contract(synthesis, request)
            if (
                request.expressive_mode == "required"
                and execution_contract["degraded_features"]
            ):
                raise HttpConnectorConfigError(
                    "expressive_feature_not_applied: "
                    + ", ".join(execution_contract["degraded_features"])
                )
            transport = SafeHttpConnectorTransport(
                base_url=self.base_url,
                api_key=self.api_key,
                auth=self.manifest.auth,
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=CONNECTOR_AUDIO_MAX_BYTES,
                require_https=True,
                opener=self._opener,
                resolver=self._resolver,
                monotonic=self._monotonic,
            )
            rendered_headers = {
                key: str(_render_template(value, context))
                for key, value in synthesis.headers.items()
            }
            if any(any(char in value for char in "\r\n") for value in rendered_headers.values()):
                raise HttpConnectorConfigError("Rendered synthesis header is invalid")
            rendered_body = _render_template(synthesis.body, context)
            if synthesis.content_type == "application/json":
                body = json.dumps(rendered_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            else:
                if not isinstance(rendered_body, Mapping):
                    raise HttpConnectorConfigError("form synthesis body must be an object")
                body = urllib.parse.urlencode(
                    {str(key): str(value) for key, value in rendered_body.items()}
                ).encode("utf-8")
            rendered_headers["Content-Type"] = synthesis.content_type
            endpoint_context = {
                key: urllib.parse.quote(str(value), safe="") if isinstance(value, str) else value
                for key, value in context.items()
            }
            endpoint = str(_render_template(synthesis.path, endpoint_context))
            response = transport.request(
                endpoint,
                method=synthesis.method,
                headers=rendered_headers,
                body=body,
                accept=(
                    "audio/*,application/octet-stream"
                    if synthesis.response.type == "binary"
                    else "application/json"
                ),
            )
            payload: Any = None
            audio: bytes | None = None
            audio_url: str | None = None
            downloaded_audio_url = False
            content_type = response.content_type
            response_mapping = synthesis.response
            supplied_duration: Any = None
            if response_mapping.type == "binary":
                audio = response.body
            else:
                try:
                    payload = json.loads(response.body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                    raise HttpConnectorRequestError("invalid_json") from exc
                if response_mapping.type == "async_json":
                    payload, response_mapping, content_type = self._poll(
                        transport=transport,
                        initial_payload=payload,
                        context=context,
                    )
                if response_mapping.type == "binary" and isinstance(payload, (bytes, bytearray)):
                    audio = bytes(payload)
                    audio_url = None
                else:
                    audio, audio_url = _decode_json_audio(
                        payload,
                        response_mapping.type,
                        response_mapping.audio_path,
                    )
                supplied_duration = json_path_get(payload, response_mapping.duration_path)
                mapped_mime = json_path_get(payload, response_mapping.mime_type_path)
                if isinstance(mapped_mime, str) and mapped_mime.strip():
                    content_type = mapped_mime.strip()
            if audio_url:
                try:
                    parsed_media_url = urllib.parse.urlsplit(audio_url)
                    same_api_origin = _origin(audio_url) == transport.origin
                except (TypeError, ValueError):
                    parsed_media_url = urllib.parse.SplitResult("", "", "", "", "")
                    same_api_origin = False
                if same_api_origin and not parsed_media_url.query:
                    # GenMax-style APIs may protect their same-origin /audio
                    # endpoint with the same xi-api-key used by synthesis. Reuse
                    # auth only on the exact validated API origin. Signed URLs
                    # and cross-origin CDN media continue through the public
                    # no-credential downloader below.
                    downloaded = transport.request(
                        audio_url,
                        method="GET",
                        accept="audio/*,application/octet-stream",
                    )
                else:
                    downloaded = _download_public_audio_url(
                        audio_url,
                        timeout_seconds=self.timeout_seconds,
                        resolver=self._resolver,
                        opener=self._opener,
                    )
                audio = downloaded.body
                content_type = downloaded.content_type or content_type
                downloaded_audio_url = True
            if not audio:
                raise HttpConnectorRequestError("empty_audio")
            raw_content_type = (content_type or "").split(";", 1)[0].strip().lower()
            configured_mime = (response_mapping.mime_type or "").split(";", 1)[0].strip().lower()
            configured_audio_mime = configured_mime.startswith("audio/") or configured_mime == "application/octet-stream"
            if (
                raw_content_type
                and not raw_content_type.startswith("audio/")
                and raw_content_type != "application/octet-stream"
                and (response_mapping.type == "binary" or downloaded_audio_url)
                and not _has_known_audio_signature(audio)
                and (not configured_audio_mime or _looks_like_text_error_payload(audio))
            ):
                raise HttpConnectorRequestError("invalid_audio_mime")
            mime, extension = _guess_audio_metadata(
                audio,
                response_mapping.mime_type,
                content_type,
                response_mapping.file_extension,
            )
            duration = _duration_seconds(
                audio,
                mime,
                supplied_duration,
                request.text,
                speaking_rate,
            )
            return TtsProviderOutput(
                audio_bytes=audio,
                duration_seconds=duration,
                mime_type=mime,
                file_extension=extension,
                provider_metadata={
                    "provider": self.provider_name,
                    "adapter": "http_connector_v1",
                    "model_id": self.model_id,
                    "voice_id": request.voice_config.voice_id,
                    "endpoints": list(transport.endpoints),
                    "response_mime_type": content_type,
                    "execution_contract": execution_contract,
                },
                warnings=list(transport.key_warnings),
            )
        except TtsPipelineError:
            raise
        except (HttpConnectorConfigError, HttpConnectorRequestError) as exc:
            code = getattr(exc, "code", "invalid_connector_config")
            if str(exc).startswith("expressive_feature_not_applied"):
                code = "expressive_feature_not_applied"
            status = getattr(exc, "http_status", None)
            detail = f"HTTP connector synthesis failed ({code}{f', HTTP {status}' if status else ''})."
            if code == "expressive_feature_not_applied":
                missing = str(exc).partition(":")[2].strip()
                if missing:
                    detail += f" Missing provider bindings: {missing}."
            provider_detail = getattr(exc, "provider_detail", "")
            if provider_detail:
                detail += f" Provider: {provider_detail}"
            if code == "invalid_audio_mime":
                detail += (
                    " The final media URL returned a non-audio payload; verify the polling audio path, "
                    "configured MIME type, and whether the provider URL is publicly downloadable."
                )
            raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, detail) from exc
        except Exception as exc:  # noqa: BLE001 - never expose vendor/client internals
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "HTTP connector synthesis failed (unexpected_client_error).",
            ) from exc

    def _poll(
        self,
        *,
        transport: SafeHttpConnectorTransport,
        initial_payload: Any,
        context: dict[str, Any],
    ) -> tuple[Any, HttpConnectorResponse, str]:
        synthesis = self.manifest.synthesis
        assert synthesis is not None and synthesis.polling is not None
        polling = synthesis.polling
        job_id = _safe_text(json_path_get(initial_payload, polling.job_id_path), secret=transport.api_key)
        if not job_id:
            raise HttpConnectorRequestError("missing_job_id")
        path_context = {**context, "job_id": urllib.parse.quote(job_id, safe="")}
        body_context = {**context, "job_id": job_id}
        poll_path = str(_render_template(polling.poll_path, path_context))
        rendered_body = _render_template(polling.body, body_context)
        poll_body: bytes | None = None
        poll_headers: dict[str, str] = {}
        if polling.method != "GET":
            if polling.content_type == "application/json":
                poll_body = json.dumps(
                    rendered_body,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            else:
                if not isinstance(rendered_body, Mapping):
                    raise HttpConnectorConfigError(
                        "form polling body must be an object"
                    )
                poll_body = urllib.parse.urlencode(
                    {str(key): str(value) for key, value in rendered_body.items()}
                ).encode("utf-8")
            poll_headers["Content-Type"] = polling.content_type
        success_values = set(polling.success_values)
        failure_values = set(polling.failure_values)
        last_payload = initial_payload
        content_type = "application/json"
        for attempt in range(polling.max_attempts):
            if attempt:
                self._sleeper(polling.interval_seconds)
            response = transport.request(
                poll_path,
                method=polling.method,
                headers=poll_headers,
                body=poll_body,
                accept="application/json",
            )
            content_type = response.content_type
            if polling.response_type == "binary":
                raw_content_type = (content_type or "").split(";", 1)[0].strip().lower()
                if (
                    raw_content_type.startswith("audio/")
                    or raw_content_type == "application/octet-stream"
                    or _has_known_audio_signature(response.body)
                ):
                    return (
                        response.body,
                        HttpConnectorResponse(
                            type="binary",
                            audio_path="",
                            mime_type=synthesis.response.mime_type,
                            mime_type_path="",
                            duration_path=synthesis.response.duration_path,
                            file_extension=synthesis.response.file_extension,
                        ),
                        content_type,
                    )
            try:
                last_payload = json.loads(response.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                raise HttpConnectorRequestError("invalid_json") from exc
            status = _safe_text(json_path_get(last_payload, polling.status_path), secret=transport.api_key).casefold()
            if status in failure_values:
                raise HttpConnectorRequestError("remote_job_failed")
            audio_path = polling.audio_path or synthesis.response.audio_path
            has_audio = bool(json_path_get(last_payload, audio_path)) if audio_path else False
            if status in success_values or (not status and has_audio):
                return (
                    last_payload,
                    HttpConnectorResponse(
                        type=polling.response_type,
                        audio_path=audio_path,
                        mime_type=synthesis.response.mime_type,
                        mime_type_path=polling.mime_type_path or synthesis.response.mime_type_path,
                        duration_path=polling.duration_path or synthesis.response.duration_path,
                        file_extension=synthesis.response.file_extension,
                    ),
                    content_type,
                )
        raise HttpConnectorRequestError("polling_exhausted")
