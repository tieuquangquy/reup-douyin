"""List available models for Ops Translation AI setup (provider-aware)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from src.audio_pipeline.translation_provider_mode import resolve_translation_provider_mode
from src.audio_pipeline.google_cloud_genai import (
    GOOGLE_CLOUD_DEFAULT_REGION,
    GOOGLE_CLOUD_FALLBACK_MODELS,
)

logger = logging.getLogger(__name__)

# When Google is unreachable (firewall / WinError 10060), still offer common ids.
GEMINI_FALLBACK_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
)

# List-models should fail fast; form timeout is for chat/test, not catalog fetch.
LIST_MODELS_TIMEOUT_CAP_SECONDS = 12.0


def model_list_ready(provider: str, *, api_key: str, base_url: str) -> bool:
    mode = resolve_translation_provider_mode(provider)
    key = (api_key or "").strip()
    base = (base_url or "").strip()
    if mode == "openai_compatible":
        return bool(key and base)
    if mode == "google_cloud":
        return bool(key)
    if mode == "gemini":
        return bool(key)
    if mode == "ollama":
        return bool(base)
    return False


def list_models_timeout_seconds(requested: float | None) -> float:
    """Clamp list-models timeout so Ops UI does not hang on dead endpoints."""
    raw = float(requested) if requested is not None else LIST_MODELS_TIMEOUT_CAP_SECONDS
    if raw <= 0:
        raw = LIST_MODELS_TIMEOUT_CAP_SECONDS
    return min(raw, LIST_MODELS_TIMEOUT_CAP_SECONDS)


def list_translation_ai_models(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    region: str = GOOGLE_CLOUD_DEFAULT_REGION,
    timeout_seconds: float = 30.0,
    opener: Any | None = None,
) -> tuple[bool, list[str], str]:
    """
    Returns (ok, models, detail).
    ok=False with empty models when credentials incomplete or provider call fails.
    For gemini connection failures, models may still contain a curated fallback list.
    """
    raw = (provider or "").strip().lower()
    mode = resolve_translation_provider_mode(raw)
    key = (api_key or "").strip()
    base = (base_url or "").strip()
    if mode == "unsupported":
        return False, [], "Select a provider (Gemini, OpenAI Compatible, Ollama, …) to load models."
    if not model_list_ready(raw, api_key=key, base_url=base):
        return False, [], "Fill required credentials for this provider before loading models."

    if mode == "google_cloud":
        # Vertex Express Mode supports API-key generation, but the Vertex
        # models.list catalog endpoint still requires OAuth2. Keep catalog
        # discovery deterministic and let Test Connection verify the selected
        # model through a real generateContent call.
        return True, list(GOOGLE_CLOUD_FALLBACK_MODELS), ""

    timeout = list_models_timeout_seconds(timeout_seconds)
    open_fn = opener or urllib.request.urlopen
    try:
        if mode == "openai_compatible":
            models = _list_openai_compatible(base, key, timeout, open_fn)
        elif mode == "gemini":
            models = _list_gemini(key, timeout, open_fn)
        elif mode == "ollama":
            models = _list_ollama(base, timeout, open_fn)
        else:
            return False, [], f"unsupported_provider:{raw}"
    except Exception as exc:  # noqa: BLE001 - surface to Ops UI
        detail = str(exc)[:400]
        logger.info("translation_ai_list_models_failed", extra={"provider": raw, "error": detail[:200]})
        if mode == "gemini" and _looks_like_connection_failure(detail):
            return False, list(GEMINI_FALLBACK_MODELS), detail
        return False, [], detail

    cleaned = sorted({m for m in models if m})
    if not cleaned:
        return False, [], "No models returned by provider."
    return True, cleaned, ""


def _looks_like_connection_failure(text: str) -> bool:
    return bool(
        re.search(
            r"urlopen|winerror\s*10060|timed?\s*out|connection\s*(attempt\s*)?failed|"
            r"connection\s*refused|name\s*or\s*service\s*not\s*known|getaddrinfo|"
            r"network\s*is\s*unreachable",
            text,
            re.I,
        )
    )


def _list_openai_compatible(base_url: str, api_key: str, timeout: float, open_fn: Any) -> list[str]:
    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="GET",
    )
    payload = _read_json(request, timeout, open_fn)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("openai_compatible_models_invalid_response")
    out: list[str] = []
    for item in data:
        if isinstance(item, dict):
            mid = str(item.get("id") or "").strip()
            if mid:
                out.append(mid)
    return out


def _list_gemini(api_key: str, timeout: float, open_fn: Any) -> list[str]:
    quoted = urllib.parse.quote(api_key, safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={quoted}"
    request = urllib.request.Request(url, method="GET")
    payload = _read_json(request, timeout, open_fn)
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("gemini_models_invalid_response")
    out: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name.startswith("models/"):
            name = name[len("models/") :]
        # Prefer generateContent-capable models when methods are advertised.
        methods = item.get("supportedGenerationMethods") or item.get("supported_generation_methods") or []
        if isinstance(methods, list) and methods and "generateContent" not in methods:
            continue
        if name:
            out.append(name)
    return out


def _list_ollama(base_url: str, timeout: float, open_fn: Any) -> list[str]:
    url = base_url.rstrip("/") + "/api/tags"
    request = urllib.request.Request(url, method="GET")
    payload = _read_json(request, timeout, open_fn)
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("ollama_tags_invalid_response")
    out: list[str] = []
    for item in rows:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                out.append(name)
    return out


def _read_json(request: urllib.request.Request, timeout: float, open_fn: Any) -> dict:
    try:
        with open_fn(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"list_models_http_{exc.code}:{detail[:200]}") from exc
