"""List available models for Ops Translation AI setup (provider-aware)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def model_list_ready(provider: str, *, api_key: str, base_url: str) -> bool:
    mode = (provider or "").strip().lower()
    key = (api_key or "").strip()
    base = (base_url or "").strip()
    if mode == "openai_compatible":
        return bool(key and base)
    if mode == "gemini":
        return bool(key)
    if mode in {"ollama", "qwen"}:
        return bool(base)
    return False


def list_translation_ai_models(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    timeout_seconds: float = 30.0,
    opener: Any | None = None,
) -> tuple[bool, list[str], str]:
    """
    Returns (ok, models, detail).
    ok=False with empty models when credentials incomplete or provider call fails.
    """
    mode = (provider or "").strip().lower()
    key = (api_key or "").strip()
    base = (base_url or "").strip()
    if mode in {"auto", "placeholder", "off", "none"}:
        return False, [], "Select gemini, openai_compatible, or ollama to load models."
    if not model_list_ready(mode, api_key=key, base_url=base):
        return False, [], "Fill required credentials for this provider before loading models."

    open_fn = opener or urllib.request.urlopen
    try:
        if mode == "openai_compatible":
            models = _list_openai_compatible(base, key, timeout_seconds, open_fn)
        elif mode == "gemini":
            models = _list_gemini(key, timeout_seconds, open_fn)
        elif mode in {"ollama", "qwen"}:
            models = _list_ollama(base, timeout_seconds, open_fn)
        else:
            return False, [], f"unsupported_provider:{mode}"
    except Exception as exc:  # noqa: BLE001 - surface to Ops UI
        logger.info("translation_ai_list_models_failed", extra={"provider": mode, "error": str(exc)[:200]})
        return False, [], str(exc)[:400]

    cleaned = sorted({m for m in models if m})
    if not cleaned:
        return False, [], "No models returned by provider."
    return True, cleaned, ""


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
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
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
