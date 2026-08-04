from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.audio_pipeline.translation_provider_mode import resolve_translation_provider_mode
from src.audio_pipeline.providers import (
    CaptionFallbackSttProvider,
    PlaceholderVietnameseTranslationProvider,
    SttProvider,
    TranslationProvider,
)
from src.audio_pipeline.stt_funasr import FunasrSttProvider
from src.audio_pipeline.translation_llm import (
    DurationConstrainedTranslationProvider,
    GeminiHttpClient,
    OllamaHttpClient,
    OpenAiCompatibleHttpClient,
)
from src.core.settings import get_settings
from src.storage.local import LocalStorageBackend, to_windows_long_path

logger = logging.getLogger(__name__)


def build_default_stt_provider(*, settings: Any | None = None, storage_root: str | None = None) -> SttProvider:
    cfg = settings or get_settings()
    root = storage_root or getattr(cfg, "local_storage_root", "./data/storage")
    storage = LocalStorageBackend(root)

    def resolve_audio_path(storage_key: str) -> str | None:
        try:
            path = storage.resolve(storage_key).absolute_path
            filesystem_path = to_windows_long_path(Path(path))
            return str(filesystem_path) if filesystem_path.exists() else None
        except Exception:
            return None

    mode = str(getattr(cfg, "audio_stt_provider", "funasr") or "funasr").strip().lower()
    if mode in {"caption", "caption_fallback"}:
        return CaptionFallbackSttProvider()
    timeout_seconds = float(getattr(cfg, "audio_funasr_timeout_seconds", 900.0) or 900.0)
    return FunasrSttProvider(resolve_audio_path=resolve_audio_path, timeout_seconds=timeout_seconds)


def build_default_translation_provider(
    *,
    settings: Any | None = None,
    workspace_ai: Any | None = None,
) -> TranslationProvider:
    cfg = settings or get_settings()
    if workspace_ai is not None and bool(getattr(workspace_ai, "enabled", False)):
        return _build_from_workspace_ai(workspace_ai, env_settings=cfg)
    return _build_from_env(cfg)


def _build_from_env(cfg: Any) -> TranslationProvider:
    mode = str(getattr(cfg, "audio_translation_provider", "auto") or "auto").strip().lower()
    if mode in {"placeholder", "off", "none"}:
        return PlaceholderVietnameseTranslationProvider()

    gemini_key = (getattr(cfg, "gemini_api_key", None) or "").strip()
    ollama_enabled = bool(getattr(cfg, "ollama_translation_enabled", True))
    ollama_base = str(getattr(cfg, "ollama_base_url", "http://127.0.0.1:11434") or "http://127.0.0.1:11434")
    ollama_model = str(getattr(cfg, "ollama_translation_model", "qwen2.5:14b") or "qwen2.5:14b")
    gemini_model = str(getattr(cfg, "gemini_translation_model", "gemini-2.5-flash") or "gemini-2.5-flash")

    gemini_interval = float(
        getattr(cfg, "gemini_translation_min_request_interval_seconds", 13.0) or 0.0
    )
    gemini = (
        GeminiHttpClient(
            api_key=gemini_key,
            model=gemini_model,
            min_request_interval_seconds=gemini_interval,
        )
        if gemini_key
        else None
    )
    ollama = OllamaHttpClient(base_url=ollama_base, model=ollama_model) if ollama_enabled else None

    if mode == "gemini":
        if gemini is None:
            logger.warning("gemini_translation_requested_without_key_using_placeholder")
            return PlaceholderVietnameseTranslationProvider()
        return DurationConstrainedTranslationProvider(
            primary=gemini,
            fallback=ollama,
            max_rewrite_rounds=2,
            allow_machine_translate_recovery=False,
        )

    if mode in {"qwen", "ollama"}:
        if ollama is None:
            return PlaceholderVietnameseTranslationProvider()
        return DurationConstrainedTranslationProvider(
            primary=ollama,
            fallback=None,
            max_rewrite_rounds=2,
            allow_machine_translate_recovery=False,
        )

    # auto
    if gemini is not None:
        return DurationConstrainedTranslationProvider(
            primary=gemini,
            fallback=ollama,
            max_rewrite_rounds=2,
            allow_machine_translate_recovery=False,
        )
    if ollama is not None:
        return DurationConstrainedTranslationProvider(
            primary=ollama,
            fallback=None,
            max_rewrite_rounds=2,
            allow_machine_translate_recovery=False,
        )
    logger.info("translation_provider_placeholder_no_llm_configured")
    return PlaceholderVietnameseTranslationProvider()


def _build_from_workspace_ai(workspace_ai: Any, *, env_settings: Any) -> TranslationProvider:
    provider = str(getattr(workspace_ai, "provider", "auto") or "auto").strip().lower()
    if provider in {"placeholder", "off", "none"}:
        return PlaceholderVietnameseTranslationProvider()

    timeout = float(getattr(workspace_ai, "timeout_seconds", 90.0) or 90.0)
    model = str(getattr(workspace_ai, "model", "") or "").strip()
    base_url = str(getattr(workspace_ai, "base_url", "") or "").strip()
    api_key = (getattr(workspace_ai, "api_key", None) or "").strip()
    fallback_name = str(getattr(workspace_ai, "fallback_provider", "none") or "none").strip().lower()
    fallback_model = str(getattr(workspace_ai, "fallback_model", "") or "").strip()

    primary = _make_llm_client(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout,
        env_settings=env_settings,
        prefer_env_key_when_empty=True,
    )
    if primary is None and provider == "auto":
        return _build_from_env(env_settings)
    if primary is None:
        logger.warning(
            "workspace_translation_ai_missing_client",
            extra={"provider": provider},
        )
        return PlaceholderVietnameseTranslationProvider()

    fallback = None
    if fallback_name not in {"", "none"}:
        fallback = _make_llm_client(
            provider=fallback_name,
            model=fallback_model,
            api_key="",
            base_url="",
            timeout_seconds=timeout,
            env_settings=env_settings,
            prefer_env_key_when_empty=True,
        )

    return DurationConstrainedTranslationProvider(
        primary=primary,
        fallback=fallback,
        max_rewrite_rounds=2,
        allow_machine_translate_recovery=False,
    )


def _make_llm_client(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    env_settings: Any,
    prefer_env_key_when_empty: bool,
) -> Any | None:
    raw = provider.strip().lower()
    if raw == "auto":
        # Prefer Gemini env, then Ollama when workspace says auto.
        gemini = _make_llm_client(
            provider="gemini",
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            env_settings=env_settings,
            prefer_env_key_when_empty=prefer_env_key_when_empty,
        )
        if gemini is not None:
            return gemini
        return _make_llm_client(
            provider="ollama",
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            env_settings=env_settings,
            prefer_env_key_when_empty=prefer_env_key_when_empty,
        )

    mode = resolve_translation_provider_mode(raw)
    if mode == "gemini":
        key = api_key or (
            (getattr(env_settings, "gemini_api_key", None) or "").strip() if prefer_env_key_when_empty else ""
        )
        chosen_model = model or str(
            getattr(env_settings, "gemini_translation_model", "gemini-2.5-flash") or "gemini-2.5-flash"
        )
        if not key:
            return None
        return GeminiHttpClient(
            api_key=key,
            model=chosen_model,
            timeout_seconds=timeout_seconds,
            min_request_interval_seconds=float(
                getattr(env_settings, "gemini_translation_min_request_interval_seconds", 13.0)
                or 0.0
            ),
        )

    if mode == "ollama":
        chosen_base = base_url or str(
            getattr(env_settings, "ollama_base_url", "http://127.0.0.1:11434") or "http://127.0.0.1:11434"
        )
        chosen_model = model or str(
            getattr(env_settings, "ollama_translation_model", "qwen2.5:14b") or "qwen2.5:14b"
        )
        return OllamaHttpClient(base_url=chosen_base, model=chosen_model, timeout_seconds=timeout_seconds)

    if mode == "openai_compatible":
        key = api_key
        if not key and prefer_env_key_when_empty:
            # No dedicated env yet; require workspace key for third-party.
            key = ""
        chosen_base = base_url or "https://api.openai.com/v1"
        if not key or not model:
            return None
        return OpenAiCompatibleHttpClient(
            api_key=key,
            model=model,
            base_url=chosen_base,
            timeout_seconds=timeout_seconds,
            provider_name=raw or "openai_compatible",
        )

    return None


def probe_translation_ai_client(workspace_ai: Any, *, settings: Any | None = None) -> tuple[bool, str, str]:
    """
    Smoke-test the primary LLM client.
    Returns (ok, provider_name, detail).

    Ops Test Connection always probes the provided draft credentials. The
    workspace ``enabled`` flag only gates runtime pipeline use of the override
    (see ``build_default_translation_provider``); it must not redirect Test to
    env Gemini when the operator is validating an Off draft form.
    """
    cfg = settings or get_settings()
    if workspace_ai is None:
        provider = build_default_translation_provider(settings=cfg, workspace_ai=None)
    else:
        provider = _build_from_workspace_ai(workspace_ai, env_settings=cfg)
    if isinstance(provider, PlaceholderVietnameseTranslationProvider):
        return False, "placeholder", "No LLM client configured (missing key/model/base URL)."
    primary = getattr(provider, "primary", None)
    if primary is None or not hasattr(primary, "complete"):
        return False, "unknown", "Translation provider has no completable primary client."
    name = str(getattr(primary, "provider_name", "unknown"))
    try:
        text = primary.complete("Reply with exactly: OK")
    except Exception as exc:  # noqa: BLE001 - surface provider errors to Ops UI
        return False, name, str(exc)[:400]
    sample = (text or "").strip()[:120]
    if not sample:
        return False, name, "empty_response"
    return True, name, sample
