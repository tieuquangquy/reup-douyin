"""Cached, secret-safe health gate for durable translation jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from src.audio_pipeline.provider_factory import probe_translation_ai_client
from src.core.settings import get_settings
from src.services.pipeline_failure_context import build_pipeline_failure_context

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, "TranslationProviderPreflightResult"]] = {}


@dataclass(frozen=True)
class TranslationProviderPreflightResult:
    ok: bool
    provider: str
    detail: str
    cached: bool = False
    degraded_to_fallback: bool = False
    error_context: dict[str, Any] | None = None

    @property
    def retryable(self) -> bool:
        return bool((self.error_context or {}).get("retryable", True))


def _probe_config(workspace_ai: Any, *, timeout_seconds: float) -> Any | None:
    if workspace_ai is None or not bool(getattr(workspace_ai, "enabled", False)):
        return None
    return SimpleNamespace(
        enabled=True,
        provider=str(getattr(workspace_ai, "provider", "auto") or "auto"),
        model=str(getattr(workspace_ai, "model", "") or ""),
        api_key=getattr(workspace_ai, "api_key", None),
        base_url=str(getattr(workspace_ai, "base_url", "") or ""),
        region=str(getattr(workspace_ai, "region", "global") or "global"),
        timeout_seconds=timeout_seconds,
        fallback_provider=str(getattr(workspace_ai, "fallback_provider", "none") or "none"),
        fallback_model=str(getattr(workspace_ai, "fallback_model", "") or ""),
    )


def _fingerprint(workspace_ai: Any, settings: Any) -> str:
    values = {
        "enabled": bool(getattr(workspace_ai, "enabled", False)) if workspace_ai is not None else False,
        "provider": str(getattr(workspace_ai, "provider", "") or "") if workspace_ai is not None else "env",
        "model": str(getattr(workspace_ai, "model", "") or "") if workspace_ai is not None else "",
        "base_url": str(getattr(workspace_ai, "base_url", "") or "") if workspace_ai is not None else "",
        "region": str(getattr(workspace_ai, "region", "global") or "global") if workspace_ai is not None else "global",
        "fallback_provider": str(getattr(workspace_ai, "fallback_provider", "") or "") if workspace_ai is not None else "",
        "fallback_model": str(getattr(workspace_ai, "fallback_model", "") or "") if workspace_ai is not None else "",
        # Hash credentials into the cache key; never store or log them.
        "workspace_key_sha256": hashlib.sha256(
            str(getattr(workspace_ai, "api_key", "") or "").encode("utf-8")
        ).hexdigest(),
        "env_provider": str(getattr(settings, "audio_translation_provider", "") or ""),
        "env_gemini_key_sha256": hashlib.sha256(
            str(getattr(settings, "gemini_api_key", "") or "").encode("utf-8")
        ).hexdigest(),
        "env_ollama_model": str(getattr(settings, "ollama_translation_model", "") or ""),
    }
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def clear_translation_provider_preflight_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def preflight_translation_provider(
    workspace_ai: Any,
    *,
    settings: Any | None = None,
    force: bool = False,
) -> TranslationProviderPreflightResult:
    cfg = settings or get_settings()
    if not bool(getattr(cfg, "translation_provider_preflight_enabled", True)):
        return TranslationProviderPreflightResult(
            ok=True,
            provider="preflight_disabled",
            detail="preflight_disabled",
        )

    cache_key = _fingerprint(workspace_ai, cfg)
    now = time.monotonic()
    if not force:
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
        if cached and cached[0] > now:
            result = cached[1]
            return TranslationProviderPreflightResult(
                **{**result.__dict__, "cached": True}
            )

    timeout = max(
        2.0,
        min(30.0, float(getattr(cfg, "translation_provider_preflight_timeout_seconds", 12.0) or 12.0)),
    )
    probe_cfg = _probe_config(workspace_ai, timeout_seconds=timeout)
    ok, provider, detail = probe_translation_ai_client(
        probe_cfg,
        settings=cfg,
        allow_fallback=True,
    )
    degraded = ok and detail.startswith("fallback_ok:")
    error_context = None
    if not ok:
        classification_detail = detail
        if detail.startswith("fallback="):
            classification_detail = detail.split("; primary=", 1)[0].removeprefix("fallback=")
        error_context = build_pipeline_failure_context(
            failed_step="translate",
            error_code="translation_failed",
            error_message=f"translation_provider_preflight_failed:{classification_detail}",
        )
    result = TranslationProviderPreflightResult(
        ok=ok,
        provider=provider,
        detail=detail,
        degraded_to_fallback=degraded,
        error_context=error_context,
    )
    ttl_name = (
        "translation_provider_preflight_success_ttl_seconds"
        if ok
        else "translation_provider_preflight_failure_ttl_seconds"
    )
    ttl = max(0, int(getattr(cfg, ttl_name, 300 if ok else 30) or 0))
    if ttl:
        with _CACHE_LOCK:
            _CACHE[cache_key] = (now + ttl, result)
    logger.info(
        "translation_provider_preflight",
        extra={
            "ok": ok,
            "provider": provider,
            "degraded_to_fallback": degraded,
            "http_status": (error_context or {}).get("http_status"),
            "provider_error_code": (error_context or {}).get("provider_error_code"),
        },
    )
    return result
