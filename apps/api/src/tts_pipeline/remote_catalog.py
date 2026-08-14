"""Safe, provider-aware TTS catalog discovery for remote HTTP APIs.

The Ops form passes draft credentials to ``POST /ops/tts-ai/test``.  This
module deliberately keeps discovery separate from synthesis adapters: it only
performs bounded, read-only JSON ``GET`` requests and returns UI-safe catalog
metadata.  Credential values and remote response bodies are never included in
errors, logs, or the returned catalog.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from src.tts_pipeline.catalog import (
    TtsCatalogDiscovery,
    TtsLanguageOption,
    TtsModelOption,
    TtsProviderCatalog,
    TtsVoiceOption,
    capabilities_for_provider,
)

REMOTE_CATALOG_TIMEOUT_CAP_SECONDS = 10.0
REMOTE_CATALOG_TIMEOUT_DEFAULT_SECONDS = 8.0
REMOTE_CATALOG_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REMOTE_CATALOG_MAX_OPTIONS = 500

REMOTE_TTS_DEFAULT_BASE_URLS: Mapping[str, str] = MappingProxyType(
    {
        "openai": "https://api.openai.com/v1",
        "elevenlabs": "https://api.elevenlabs.io/v1",
        "google": "https://texttospeech.googleapis.com/v1",
    }
)

_PUBLIC_ERROR_MESSAGES = {
    "deadline_exceeded": "Catalog discovery timed out.",
    "timeout": "Catalog discovery timed out.",
    "invalid_base_url": "Base URL must be a valid public HTTP(S) API URL.",
    "insecure_credentials": "HTTPS is required when an API key is supplied.",
    "invalid_api_key": "API key contains invalid characters or is too long.",
    "ssrf_blocked": "Base URL resolves to a private or restricted network address.",
    "dns_failed": "Base URL host could not be resolved.",
    "cross_origin_redirect": "Catalog endpoint redirected to a different origin.",
    "response_too_large": "Catalog response exceeded the safe size limit.",
    "invalid_json": "Catalog endpoint did not return valid JSON.",
    "invalid_response": "Catalog endpoint returned an unsupported response shape.",
    "empty_response": "Catalog endpoint returned no options.",
    "connection_error": "Catalog endpoint could not be reached.",
}


class _CatalogFetchError(RuntimeError):
    """Internal error carrying only a safe machine code and optional HTTP status."""

    def __init__(self, code: str, *, http_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def remote_catalog_timeout_seconds(requested: float | None) -> float:
    """Clamp discovery independently from the much longer synthesis timeout."""

    try:
        value = float(requested) if requested is not None else REMOTE_CATALOG_TIMEOUT_DEFAULT_SECONDS
    except (TypeError, ValueError):
        value = REMOTE_CATALOG_TIMEOUT_DEFAULT_SECONDS
    if value <= 0:
        value = REMOTE_CATALOG_TIMEOUT_DEFAULT_SECONDS
    return min(value, REMOTE_CATALOG_TIMEOUT_CAP_SECONDS)


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise _CatalogFetchError("invalid_base_url") from exc
    return scheme, host, port


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward Authorization headers to another host on redirects."""

    def __init__(self, allowed_origin: tuple[str, str, int]):
        super().__init__()
        self.allowed_origin = allowed_origin

    def redirect_request(  # noqa: PLR0913 - stdlib callback signature
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
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
            raise _CatalogFetchError("cross_origin_redirect")
        if _origin(newurl) != self.allowed_origin:
            raise _CatalogFetchError("cross_origin_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


Resolver = Callable[..., Sequence[tuple[Any, ...]]]
OpenFunction = Callable[..., Any]


def _normalize_base_url(raw: str, *, api_key: str, resolver: Resolver) -> str:
    value = (raw or "").strip().rstrip("/")
    if len(api_key) > 4096 or any(char in api_key for char in "\r\n"):
        raise _CatalogFetchError("invalid_api_key")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise _CatalogFetchError("invalid_base_url") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise _CatalogFetchError("invalid_base_url")
    if any(segment in {".", ".."} for segment in parsed.path.split("/")):
        raise _CatalogFetchError("invalid_base_url")
    if api_key and parsed.scheme.lower() != "https":
        raise _CatalogFetchError("insecure_credentials")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise _CatalogFetchError("ssrf_blocked")
    resolved_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        rows = resolver(hostname, resolved_port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise _CatalogFetchError("dns_failed") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for row in rows:
        try:
            raw_ip = row[4][0]
            addresses.append(ipaddress.ip_address(str(raw_ip).split("%", 1)[0]))
        except (IndexError, TypeError, ValueError):
            continue
    if not addresses:
        raise _CatalogFetchError("dns_failed")
    if any(not address.is_global for address in addresses):
        raise _CatalogFetchError("ssrf_blocked")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


class _SafeJsonTransport:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        opener: OpenFunction | None,
        resolver: Resolver,
        monotonic: Callable[[], float],
    ) -> None:
        self._monotonic = monotonic
        self._deadline = monotonic() + remote_catalog_timeout_seconds(timeout_seconds)
        self.base_url = _normalize_base_url(base_url, api_key=api_key, resolver=resolver)
        self.origin = _origin(self.base_url)
        if opener is None:
            director = urllib.request.build_opener(_SameOriginRedirectHandler(self.origin))
            self._open: OpenFunction = director.open
        else:
            # Test/custom transports remain responsible for redirect handling.
            self._open = opener
        self.endpoints: list[str] = []

    def get_json(self, path: str, *, headers: Mapping[str, str]) -> Any:
        remaining = self._deadline - self._monotonic()
        if remaining <= 0:
            raise _CatalogFetchError("deadline_exceeded")
        normalized_path = "/" + path.strip().lstrip("/")
        self.endpoints.append(normalized_path)
        base_path = urllib.parse.urlsplit(self.base_url).path.rstrip("/").lower()
        url = self.base_url if base_path.endswith(normalized_path.lower()) else self.base_url + normalized_path
        if _origin(url) != self.origin:
            raise _CatalogFetchError("invalid_base_url")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "reup-douyin-tts-catalog/1",
                **dict(headers),
            },
            method="GET",
        )
        try:
            with self._open(request, timeout=max(0.05, remaining)) as response:
                raw = response.read(REMOTE_CATALOG_MAX_RESPONSE_BYTES + 1)
        except _CatalogFetchError:
            raise
        except urllib.error.HTTPError as exc:
            # Never read/surface the body: vendors sometimes echo credentials.
            raise _CatalogFetchError(f"http_{exc.code}", http_status=int(exc.code)) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise _CatalogFetchError("timeout") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise _CatalogFetchError("connection_error") from exc
        if len(raw) > REMOTE_CATALOG_MAX_RESPONSE_BYTES:
            raise _CatalogFetchError("response_too_large")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _CatalogFetchError("invalid_json") from exc


@dataclass(frozen=True)
class RemoteCatalogAdapterSpec:
    """Declarative endpoint/auth layout for one remote provider family."""

    models_paths: tuple[str, ...] = ("/models",)
    voices_paths: tuple[str, ...] = ("/voices", "/audio/voices")
    languages_paths: tuple[str, ...] = ("/languages", "/audio/languages")
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    fallback_voices: tuple[tuple[str, str], ...] = ()

    def headers(self, api_key: str) -> dict[str, str]:
        if not api_key:
            return {}
        return {self.auth_header: f"{self.auth_prefix}{api_key}"}


class RemoteCatalogAdapter(Protocol):
    def discover(
        self,
        *,
        provider: str,
        transport: _SafeJsonTransport,
        api_key: str,
        language_code: str,
    ) -> TtsProviderCatalog: ...


@dataclass
class _CatalogAccumulator:
    secrets: tuple[str, ...]
    requested_language: str = ""
    models: dict[str, TtsModelOption] = field(default_factory=dict)
    voices: dict[str, TtsVoiceOption] = field(default_factory=dict)
    languages: dict[str, TtsLanguageOption] = field(default_factory=dict)
    default_model_id: str = ""
    default_voice_id: str = ""
    default_language_code: str = ""

    def identifier(self, value: Any, *, limit: int = 256) -> str:
        text = str(value or "").strip()[:limit]
        if not text or any(secret and secret in text for secret in self.secrets):
            return ""
        return text

    def text(self, value: Any, *, fallback: str = "", limit: int = 500) -> str:
        text = str(value or "").strip()[:limit]
        if any(secret and secret in text for secret in self.secrets):
            return fallback
        return text or fallback

    def add_language(self, code: Any, label: Any = "") -> str:
        key = self.identifier(code, limit=64)
        if not key or len(self.languages) >= REMOTE_CATALOG_MAX_OPTIONS:
            return ""
        if key not in self.languages:
            self.languages[key] = TtsLanguageOption(
                code=key,
                label=self.text(label, fallback=key, limit=160),
            )
        return key

    def add_voice(
        self,
        voice_id: Any,
        *,
        label: Any = "",
        languages: Sequence[str] = (),
        models: Sequence[str] = (),
        gender: Any = "",
        description: Any = "",
        capabilities: Sequence[str] = (),
    ) -> str:
        key = self.identifier(voice_id)
        if not key or (key not in self.voices and len(self.voices) >= REMOTE_CATALOG_MAX_OPTIONS):
            return ""
        safe_languages = _unique(self.identifier(value, limit=64) for value in languages)
        safe_models = _unique(self.identifier(value) for value in models)
        safe_capabilities = _unique(self.text(value, limit=120) for value in capabilities)
        existing = self.voices.get(key)
        if existing:
            existing.languages = _unique([*existing.languages, *safe_languages])
            existing.models = _unique([*existing.models, *safe_models])
            existing.capabilities = _unique([*existing.capabilities, *safe_capabilities])
            return key
        self.voices[key] = TtsVoiceOption(
            id=key,
            label=self.text(label, fallback=key, limit=200),
            languages=safe_languages,
            models=safe_models,
            gender=self.text(gender, limit=40) or None,
            description=self.text(description, limit=500) or None,
            capabilities=safe_capabilities,
        )
        return key

    def add_model(
        self,
        model_id: Any,
        *,
        label: Any = "",
        languages: Sequence[str] = (),
        voices: Sequence[str] = (),
        description: Any = "",
        capabilities: Sequence[str] = (),
    ) -> str:
        key = self.identifier(model_id)
        if not key or (key not in self.models and len(self.models) >= REMOTE_CATALOG_MAX_OPTIONS):
            return ""
        safe_languages = _unique(self.identifier(value, limit=64) for value in languages)
        safe_voices = _unique(self.identifier(value) for value in voices)
        safe_capabilities = _unique(self.text(value, limit=120) for value in capabilities)
        existing = self.models.get(key)
        if existing:
            existing.languages = _unique([*existing.languages, *safe_languages])
            existing.voices = _unique([*existing.voices, *safe_voices])
            existing.capabilities = _unique([*existing.capabilities, *safe_capabilities])
            return key
        self.models[key] = TtsModelOption(
            id=key,
            label=self.text(label, fallback=key, limit=200),
            languages=safe_languages,
            voices=safe_voices,
            description=self.text(description, limit=500) or None,
            capabilities=safe_capabilities,
        )
        return key


def _unique(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def _rows(payload: Any, keys: tuple[str, ...]) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    nested = payload.get("data")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if isinstance(value, list):
                return value
    return None


def _nested_values(row: Mapping[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for source in (row, row.get("capabilities"), row.get("metadata"), row.get("labels")):
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            value = source.get(key)
            if isinstance(value, (list, tuple, set)):
                return list(value)
            if isinstance(value, str) and value.strip():
                return [value]
    return []


def _language_values(row: Mapping[str, Any]) -> list[Any]:
    values: list[Any] = []
    single = (
        row.get("language_code")
        or row.get("languageCode")
        or row.get("locale")
        or row.get("Locale")
        or row.get("language_id")
    )
    if single:
        values.append(single)
    values.extend(_nested_values(
        row,
        (
            "languages",
            "language_codes",
            "languageCodes",
            "supported_languages",
            "supportedLanguages",
            "locales",
            "SecondaryLocaleList",
            "language_id",
            "language",
        ),
    ))
    return values


def _language_value_code(value: Any, acc: _CatalogAccumulator) -> str:
    if isinstance(value, Mapping):
        value = (
            value.get("code")
            or value.get("language_code")
            or value.get("languageCode")
            or value.get("locale")
            or value.get("id")
            or value.get("language_id")
            or value.get("language")
        )
    return acc.identifier(value, limit=64)


def _language_matches(requested: str, candidate: str) -> bool:
    requested_key = requested.strip().lower().replace("_", "-")
    candidate_key = candidate.strip().lower().replace("_", "-")
    if not requested_key or not candidate_key:
        return False
    return (
        requested_key == candidate_key
        or requested_key.split("-", 1)[0] == candidate_key.split("-", 1)[0]
    )


def _rows_for_requested_language(
    rows: list[Any],
    acc: _CatalogAccumulator,
) -> list[Any]:
    requested = acc.identifier(acc.requested_language, limit=64)
    if not requested:
        return rows
    matching: list[Any] = []
    unknown: list[Any] = []
    for row in rows:
        if not isinstance(row, Mapping):
            unknown.append(row)
            continue
        codes = [_language_value_code(value, acc) for value in _language_values(row)]
        codes = [code for code in codes if code]
        if not codes:
            unknown.append(row)
        elif any(_language_matches(requested, code) for code in codes):
            matching.append(row)
    # If the provider advertises the requested locale, omit explicitly unrelated
    # rows before applying the global 500-option cap. Unknown rows stay available.
    return [*matching, *unknown] if matching else rows


def _language_references(row: Mapping[str, Any], acc: _CatalogAccumulator) -> list[str]:
    output: list[str] = []
    values = _language_values(row)
    for value in values:
        if isinstance(value, Mapping):
            code = (
                value.get("code")
                or value.get("language_code")
                or value.get("languageCode")
                or value.get("locale")
                or value.get("id")
                or value.get("language_id")
            )
            label = value.get("label") or value.get("name") or value.get("native_name") or code
        else:
            code = value
            label = value
        added = acc.add_language(code, label)
        if added:
            output.append(added)
    return _unique(output)


def _reference_ids(values: Sequence[Any], acc: _CatalogAccumulator) -> list[str]:
    output: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            raw = (
                value.get("id")
                or value.get("voice_id")
                or value.get("voiceId")
                or value.get("model_id")
                or value.get("modelId")
                or value.get("name")
            )
        else:
            raw = value
        cleaned = acc.identifier(raw)
        if cleaned:
            output.append(cleaned)
    return _unique(output)


def _capability_values(row: Mapping[str, Any]) -> list[str]:
    """Extract small, display-safe capability/modality labels from vendor metadata."""

    values: list[str] = []
    for key in ("modalities", "capabilities", "supported_modalities", "features"):
        raw = row.get(key)
        if isinstance(raw, Mapping):
            values.extend(str(name) for name, enabled in raw.items() if enabled)
        elif isinstance(raw, (list, tuple, set)):
            values.extend(str(item) for item in raw)
        elif isinstance(raw, str) and raw.strip():
            values.append(raw)
    return _unique(value.strip()[:120] for value in values if value and value.strip())


def _parse_models(payload: Any, acc: _CatalogAccumulator) -> int:
    before = len(acc.models)
    rows = _rows(payload, ("data", "models", "items", "results"))
    if rows is None:
        raise _CatalogFetchError("invalid_response")
    parsed = 0
    for row in _rows_for_requested_language(rows, acc):
        if isinstance(row, str):
            parsed += bool(acc.add_model(row))
            continue
        if not isinstance(row, Mapping):
            continue
        capabilities = row.get("capabilities")
        explicit_tts = row.get("can_do_text_to_speech")
        if explicit_tts is None and isinstance(capabilities, Mapping):
            explicit_tts = capabilities.get("can_do_text_to_speech")
        if explicit_tts is False:
            continue
        model_id = (
            row.get("id")
            or row.get("model_id")
            or row.get("modelId")
            or row.get("model_name")
            or row.get("modelName")
            or row.get("slug")
            or row.get("name")
            or row.get("model")
        )
        languages = _language_references(row, acc)
        voice_values = _nested_values(
            row,
            ("voices", "voice_ids", "voiceIds", "supported_voices", "supportedVoices"),
        )
        voices = _reference_ids(voice_values, acc)
        parsed += bool(acc.add_model(
            model_id,
            label=row.get("display_name") or row.get("displayName") or row.get("label") or row.get("name"),
            languages=languages,
            voices=voices,
            description=row.get("description") or row.get("details"),
            capabilities=_capability_values(row),
        ))
    if isinstance(payload, Mapping):
        acc.default_model_id = acc.identifier(
            payload.get("default_model_id") or payload.get("defaultModelId") or acc.default_model_id
        )
    return parsed or len(acc.models) - before


def _parse_voices(payload: Any, acc: _CatalogAccumulator) -> int:
    before = len(acc.voices)
    rows = _rows(payload, ("voices", "data", "items", "results"))
    if rows is None:
        raise _CatalogFetchError("invalid_response")
    parsed = 0
    for row in _rows_for_requested_language(rows, acc):
        if isinstance(row, str):
            parsed += bool(acc.add_voice(row))
            continue
        if not isinstance(row, Mapping):
            continue
        voice_id = (
            row.get("id")
            or row.get("voice_id")
            or row.get("voiceId")
            or row.get("short_name")
            or row.get("ShortName")
            or row.get("voice_name")
            or row.get("voiceName")
            or row.get("Name")
            or row.get("name")
        )
        languages = _language_references(row, acc)
        models = _reference_ids(
            _nested_values(
                row,
                (
                    "models",
                    "model_ids",
                    "modelIds",
                    "supported_models",
                    "high_quality_base_model_ids",
                ),
            ),
            acc,
        )
        labels = row.get("labels") if isinstance(row.get("labels"), Mapping) else {}
        parsed += bool(acc.add_voice(
            voice_id,
            label=(
                row.get("display_name")
                or row.get("displayName")
                or row.get("label")
                or row.get("FriendlyName")
                or row.get("DisplayName")
                or row.get("LocalName")
                or row.get("Name")
                or row.get("name")
            ),
            languages=languages,
            models=models,
            gender=row.get("gender") or row.get("Gender") or row.get("ssmlGender") or labels.get("gender"),
            description=row.get("description") or row.get("details"),
            capabilities=_capability_values(row),
        ))
    if isinstance(payload, Mapping):
        acc.default_voice_id = acc.identifier(
            payload.get("default_voice_id") or payload.get("defaultVoiceId") or acc.default_voice_id
        )
    return parsed or len(acc.voices) - before


def _parse_languages(payload: Any, acc: _CatalogAccumulator) -> int:
    before = len(acc.languages)
    rows = _rows(payload, ("languages", "data", "items", "results"))
    if rows is None:
        raise _CatalogFetchError("invalid_response")
    parsed = 0
    for row in rows:
        if isinstance(row, str):
            parsed += bool(acc.add_language(row))
            continue
        if not isinstance(row, Mapping):
            continue
        code = (
            row.get("code")
            or row.get("language_code")
            or row.get("languageCode")
            or row.get("locale")
            or row.get("Locale")
            or row.get("language_id")
            or row.get("language")
            or row.get("id")
        )
        label = row.get("label") or row.get("name") or row.get("native_name") or row.get("nativeName") or code
        parsed += bool(acc.add_language(code, label))
    if isinstance(payload, Mapping):
        acc.default_language_code = acc.identifier(
            payload.get("default_language_code")
            or payload.get("defaultLanguageCode")
            or acc.default_language_code,
            limit=64,
        )
    return parsed or len(acc.languages) - before


Parser = Callable[[Any, _CatalogAccumulator], int]


def _safe_warning(resource: str, error: _CatalogFetchError) -> str:
    if error.http_status is not None:
        if error.http_status in {401, 403}:
            return f"{resource} catalog authentication was rejected (HTTP {error.http_status})."
        if error.http_status == 429:
            return f"{resource} catalog is rate limited (HTTP 429); retry later."
        if error.http_status >= 500:
            return f"{resource} catalog provider is temporarily unavailable (HTTP {error.http_status})."
        return f"{resource} catalog request returned HTTP {error.http_status}."
    message = _PUBLIC_ERROR_MESSAGES.get(error.code, "Catalog endpoint could not be read.")
    return f"{resource} catalog: {message}"


def _fetch_first(
    *,
    resource: str,
    paths: tuple[str, ...],
    parser: Parser,
    transport: _SafeJsonTransport,
    headers: Mapping[str, str],
    acc: _CatalogAccumulator,
) -> tuple[bool, str | None, str | None]:
    if not paths:
        return False, None, None
    last_error: _CatalogFetchError | None = None
    for path in paths:
        try:
            payload = transport.get_json(path, headers=headers)
            option_count = parser(payload, acc)
            if option_count > 0:
                return True, None, None
            last_error = _CatalogFetchError("empty_response")
            continue
        except _CatalogFetchError as exc:
            last_error = exc
            if exc.http_status == 404 or exc.code in {"invalid_response", "empty_response"}:
                continue
            break
    final_error = last_error or _CatalogFetchError("invalid_response")
    error_code = "authentication_failed" if final_error.http_status in {401, 403} else final_error.code
    return False, _safe_warning(resource, final_error), error_code


class StructuredRemoteCatalogAdapter:
    """Common parser with provider-specific endpoint/auth specs."""

    def __init__(self, spec: RemoteCatalogAdapterSpec):
        self.spec = spec

    def discover(
        self,
        *,
        provider: str,
        transport: _SafeJsonTransport,
        api_key: str,
        language_code: str,
    ) -> TtsProviderCatalog:
        acc = _CatalogAccumulator(secrets=(api_key,), requested_language=language_code)
        headers = self.spec.headers(api_key)
        warnings: list[str] = []
        hits: dict[str, bool] = {}
        error_code = ""
        for resource, paths, parser in (
            ("Model", self.spec.models_paths, _parse_models),
            ("Voice", self.spec.voices_paths, _parse_voices),
            ("Language", self.spec.languages_paths, _parse_languages),
        ):
            if not paths:
                continue
            hit, warning, endpoint_error = _fetch_first(
                resource=resource,
                paths=paths,
                parser=parser,
                transport=transport,
                headers=headers,
                acc=acc,
            )
            hits[resource.lower()] = hit
            if warning:
                warnings.append(warning)
            if endpoint_error and not error_code:
                error_code = endpoint_error
            if endpoint_error == "authentication_failed":
                break

        if not acc.voices and self.spec.fallback_voices:
            for voice_id, label in self.spec.fallback_voices:
                acc.add_voice(voice_id, label=label)
            if acc.voices:
                warnings.append("Voice choices use provider presets because no voice-list endpoint is available.")

        capabilities = capabilities_for_provider(provider)
        if not self.spec.models_paths:
            capabilities.model = False
            warnings.append("Provider selects the synthesis model through its voice or voice family.")

        requested_language = acc.identifier(language_code, limit=64)
        default_model = acc.default_model_id if acc.default_model_id in acc.models else ""
        default_voice = acc.default_voice_id if acc.default_voice_id in acc.voices else ""
        default_language = (
            acc.default_language_code
            if acc.default_language_code in acc.languages
            else requested_language
            if requested_language in acc.languages
            else next(iter(acc.languages), requested_language)
        )
        if not default_model:
            default_model = next(iter(acc.models), "")
        if not default_voice:
            default_voice = next(iter(acc.voices), "")

        has_data = bool(acc.models or acc.voices or acc.languages)
        expected_hits = [hits[key] for key in ("model", "voice", "language") if key in hits]
        if has_data and expected_hits and all(expected_hits):
            discovery_status = "complete"
        elif has_data:
            discovery_status = "partial"
        else:
            discovery_status = "unavailable"
        return TtsProviderCatalog(
            source="provider" if has_data else "none",
            voices=list(acc.voices.values()),
            models=list(acc.models),
            model_options=list(acc.models.values()),
            languages=list(acc.languages.values()),
            default_voice_id=default_voice,
            default_model_id=default_model,
            default_language_code=default_language,
            warning=" ".join(_unique(warnings)),
            capabilities=capabilities,
            discovery=TtsCatalogDiscovery(
                status=discovery_status,
                endpoints=_unique(transport.endpoints),
                warnings=_unique(warnings),
                error_code=error_code,
            ),
        )


_OPENAI_TTS_MODEL_IDS = frozenset({"tts-1", "tts-1-hd", "gpt-4o-mini-tts"})

_OPENAI_VOICE_PRESETS = (
    ("alloy", "alloy"),
    ("ash", "ash"),
    ("ballad", "ballad"),
    ("coral", "coral"),
    ("echo", "echo"),
    ("fable", "fable"),
    ("sage", "sage"),
    ("verse", "verse"),
    ("marin", "marin"),
    ("cedar", "cedar"),
    # Legacy voices remain selectable for compatible accounts/endpoints.
    ("nova", "nova"),
    ("onyx", "onyx"),
    ("shimmer", "shimmer"),
)


class OpenAiRemoteCatalogAdapter(StructuredRemoteCatalogAdapter):
    """OpenAI lists every API model, so retain only documented TTS ids."""

    def discover(
        self,
        *,
        provider: str,
        transport: _SafeJsonTransport,
        api_key: str,
        language_code: str,
    ) -> TtsProviderCatalog:
        catalog = super().discover(
            provider=provider,
            transport=transport,
            api_key=api_key,
            language_code=language_code,
        )
        catalog.model_options = [
            option for option in catalog.model_options if option.id in _OPENAI_TTS_MODEL_IDS
        ]
        catalog.models = [model for model in catalog.models if model in _OPENAI_TTS_MODEL_IDS]
        catalog.default_model_id = catalog.models[0] if catalog.models else ""
        if not catalog.models:
            warning = "OpenAI returned no supported TTS model ids."
            existing = catalog.discovery.warnings if catalog.discovery else []
            if warning not in existing:
                existing.append(warning)
            catalog.warning = " ".join(_unique([catalog.warning, warning]))
            if catalog.discovery:
                catalog.discovery.status = "partial" if catalog.voices else "unavailable"
        return catalog


REMOTE_TTS_CATALOG_ADAPTERS: Mapping[str, RemoteCatalogAdapter] = MappingProxyType(
    {
        "openai_compatible": StructuredRemoteCatalogAdapter(RemoteCatalogAdapterSpec()),
        "http_custom": StructuredRemoteCatalogAdapter(RemoteCatalogAdapterSpec()),
        "openai": OpenAiRemoteCatalogAdapter(
            RemoteCatalogAdapterSpec(
                voices_paths=(),
                languages_paths=(),
                fallback_voices=_OPENAI_VOICE_PRESETS,
            )
        ),
        "elevenlabs": StructuredRemoteCatalogAdapter(
            RemoteCatalogAdapterSpec(
                voices_paths=("/voices",),
                languages_paths=(),
                auth_header="xi-api-key",
                auth_prefix="",
            )
        ),
        "google": StructuredRemoteCatalogAdapter(
            RemoteCatalogAdapterSpec(
                models_paths=(),
                voices_paths=("/voices",),
                languages_paths=(),
                auth_header="x-goog-api-key",
                auth_prefix="",
            )
        ),
        "azure": StructuredRemoteCatalogAdapter(
            RemoteCatalogAdapterSpec(
                models_paths=(),
                voices_paths=("/cognitiveservices/voices/list",),
                languages_paths=(),
                auth_header="Ocp-Apim-Subscription-Key",
                auth_prefix="",
            )
        ),
    }
)


def discover_remote_tts_catalog(
    provider: str,
    *,
    base_url: str,
    api_key: str,
    language_code: str = "vi",
    timeout_seconds: float | None = None,
    opener: OpenFunction | None = None,
    resolver: Resolver = socket.getaddrinfo,
    monotonic: Callable[[], float] = time.monotonic,
    adapters: Mapping[str, RemoteCatalogAdapter] = REMOTE_TTS_CATALOG_ADAPTERS,
    connector: Mapping[str, Any] | Any | None = None,
) -> TtsProviderCatalog | None:
    """Discover a remote catalog, or ``None`` when no adapter is registered.

    ``opener`` and ``resolver`` are injectable for deterministic tests. Production
    calls use a same-origin redirect policy and reject DNS answers pointing at
    loopback, private, link-local, multicast, reserved, or unspecified networks.
    """

    name = (provider or "").strip().lower()
    adapter = adapters.get(name)
    if adapter is None:
        return None
    # A connector manifest opts into the universal declarative adapter.  Keep
    # this branch lazy to avoid a module cycle (http_connector imports the
    # shared catalog dataclasses only).
    if connector:
        try:
            from src.tts_pipeline.http_connector import (
                HttpConnectorConfigError,
                discover_http_connector_catalog,
                parse_http_connector_manifest,
            )

            manifest = connector
            if not hasattr(connector, "auth"):
                manifest = parse_http_connector_manifest(connector)
            if manifest is None:
                raise HttpConnectorConfigError("http_connector must be an object")
            return discover_http_connector_catalog(
                name,
                base_url=(base_url or "").strip(),
                api_key=(api_key or "").strip(),
                language_code=language_code,
                timeout_seconds=timeout_seconds or REMOTE_CATALOG_TIMEOUT_DEFAULT_SECONDS,
                manifest=manifest,
                opener=opener,
                resolver=resolver,
                monotonic=monotonic,
            )
        except HttpConnectorConfigError as exc:
            warning = str(exc)[:500]
            return TtsProviderCatalog(
                source="none",
                warning=warning,
                default_language_code=(language_code or "").strip(),
                capabilities=capabilities_for_provider(name),
                discovery=TtsCatalogDiscovery(
                    status="unavailable",
                    endpoints=[],
                    warnings=[warning],
                    error_code="invalid_connector_config",
                    checks=[
                        {
                            "stage": "configuration",
                            "status": "failed",
                            "detail": warning,
                        }
                    ],
                ),
            )

    key_warnings: list[str] = []
    try:
        from src.tts_pipeline.http_connector import normalize_connector_api_key

        key, key_warnings = normalize_connector_api_key(api_key)
    except ValueError:
        return TtsProviderCatalog(
            source="none",
            warning="API key contains invalid characters or a duplicate Bearer prefix.",
            default_language_code=(language_code or "").strip(),
            capabilities=capabilities_for_provider(name),
            discovery=TtsCatalogDiscovery(
                status="unavailable",
                endpoints=[],
                warnings=["API key contains invalid characters or a duplicate Bearer prefix."],
                error_code="invalid_api_key",
            ),
        )
    resolved_base_url = (base_url or "").strip() or REMOTE_TTS_DEFAULT_BASE_URLS.get(name, "")
    try:
        transport = _SafeJsonTransport(
            base_url=resolved_base_url,
            api_key=key,
            timeout_seconds=remote_catalog_timeout_seconds(timeout_seconds),
            opener=opener,
            resolver=resolver,
            monotonic=monotonic,
        )
    except _CatalogFetchError as exc:
        warning = _PUBLIC_ERROR_MESSAGES.get(exc.code, "Remote catalog discovery is unavailable.")
        capabilities = capabilities_for_provider(name)
        adapter_spec = getattr(adapter, "spec", None)
        if adapter_spec is not None and not adapter_spec.models_paths:
            capabilities.model = False
        return TtsProviderCatalog(
            source="none",
            warning=warning,
            default_language_code=(language_code or "").strip(),
            capabilities=capabilities,
            discovery=TtsCatalogDiscovery(
                status="unavailable",
                endpoints=[],
                warnings=[warning],
                error_code=exc.code,
            ),
        )
    result = adapter.discover(
        provider=name,
        transport=transport,
        api_key=key,
        language_code=language_code,
    )
    if key_warnings:
        result.warning = " ".join(_unique([result.warning, *key_warnings]))
        if result.discovery is not None:
            result.discovery.warnings = _unique([*result.discovery.warnings, *key_warnings])
    return result
